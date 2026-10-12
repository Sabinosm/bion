from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import DoencaCronica, Paciente


class DoencaCronicaRepository(IRepository[DoencaCronica]):
    """Toda leitura "normal" filtra `deletado == False`. Além disso,
    find_por_paciente e top_cid_ativas trazem só as VIGENTES
    (encerrado_em IS NULL): linha encerrada por revisão é histórico, lido
    por find_historico_por_paciente. find_apagados é o único ponto de
    acesso a registros soft-deletados.

    Escrita: commit=True faz commit (rota granular); commit=False só faz
    flush, para compor operação atômica (acao_sensivel, rota agregada do
    binário). Delete físico levanta NotImplementedError."""

    # ------------------------------------------------------------ leitura
    def find_by_id(self, id: int) -> Optional[DoencaCronica]:
        return (
            DoencaCronica.query
            .filter(DoencaCronica.id == id, DoencaCronica.deletado == False)
            .first()
        )

    def find_by_uuid(self, uuid: str) -> Optional[DoencaCronica]:
        return (
            DoencaCronica.query
            .filter(DoencaCronica.uuid == uuid, DoencaCronica.deletado == False)
            .first()
        )

    def find_by_uuid_incluindo_deletados(self, uuid: str) -> Optional[DoencaCronica]:
        """Busca sem filtrar deletado: distingue 'não existe' de 'está removida'."""
        return DoencaCronica.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[DoencaCronica]:
        """Doenças VIGENTES (não removidas e não encerradas por revisão)."""
        return (
            DoencaCronica.query
            .filter(DoencaCronica.id_paciente == id_paciente,
                    DoencaCronica.deletado == False,
                    DoencaCronica.encerrado_em.is_(None))
            .order_by(DoencaCronica.criado_em, DoencaCronica.id)
            .all()
        )

    def find_historico_por_paciente(self, id_paciente: int) -> List[DoencaCronica]:
        """Vigentes + encerradas por revisão (não removidas), da mais
        antiga para a mais recente -- a linha do tempo de cada doença."""
        return (
            DoencaCronica.query
            .filter(DoencaCronica.id_paciente == id_paciente,
                    DoencaCronica.deletado == False)
            .order_by(DoencaCronica.criado_em, DoencaCronica.id)
            .all()
        )

    def find_aberta_por_cid(self, id_paciente: int, codigo_cid10: str,
                            ignorar_id: Optional[int] = None) -> Optional[DoencaCronica]:
        """Doença VIGENTE do paciente com o mesmo CID (barra duplicata).
        `ignorar_id` exclui a própria linha numa revisão."""
        query = (
            DoencaCronica.query
            .filter(DoencaCronica.id_paciente == id_paciente,
                    DoencaCronica.deletado == False,
                    DoencaCronica.encerrado_em.is_(None),
                    func.upper(DoencaCronica.codigo_cid10) == codigo_cid10.strip().upper())
        )
        if ignorar_id is not None:
            query = query.filter(DoencaCronica.id != ignorar_id)
        return query.first()

    def find_apagados(self, id_paciente: Optional[int] = None) -> List[DoencaCronica]:
        """Único ponto de acesso a doenças soft-deletadas (auditoria/admin)."""
        query = DoencaCronica.query.filter(DoencaCronica.deletado == True)
        if id_paciente is not None:
            query = query.filter(DoencaCronica.id_paciente == id_paciente)
        return query.all()

    # ----------------------------------------------------------- escrita
    def _persistir(self, commit: bool) -> None:
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def save(self, entity: DoencaCronica, commit: bool = True) -> DoencaCronica:
        db.session.add(entity)
        self._persistir(commit)
        return entity

    def rollback(self) -> None:
        db.session.rollback()

    def delete(self, id: int) -> bool:
        raise NotImplementedError("Doença crônica não é apagada fisicamente; use soft_delete.")

    def delete_by_uuid(self, uuid: str) -> bool:
        raise NotImplementedError("Doença crônica não é apagada fisicamente; use soft_delete.")

    def soft_delete(self, entity: DoencaCronica, motivo: str,
                    observacoes_delete: Optional[str] = None,
                    deletado_por: Optional[int] = None,
                    id_atendimento_delecao: Optional[int] = None,
                    commit: bool = True) -> DoencaCronica:
        """Marca como removida (e quem/qual atendimento) sem apagar a linha.
        Não mexe em `status` nem nos campos de encerramento."""
        entity.deletado = True
        entity.deletado_em = datetime.now(timezone.utc)
        entity.motivo_delete = motivo
        entity.observacoes_delete = observacoes_delete
        entity.deletado_por = deletado_por
        entity.id_atendimento_delecao = id_atendimento_delecao
        return self.save(entity, commit=commit)

    def restaurar(self, entity: DoencaCronica, commit: bool = True) -> DoencaCronica:
        """Reverte um soft delete (o log de auditoria da rota guarda quem restaurou)."""
        entity.deletado = False
        entity.deletado_em = None
        entity.motivo_delete = None
        entity.observacoes_delete = None
        entity.deletado_por = None
        entity.id_atendimento_delecao = None
        return self.save(entity, commit=commit)

    def substituir(self, antiga: DoencaCronica, nova: DoencaCronica,
                   encerrado_por: int, id_atendimento_encerramento: int,
                   commit: bool = True) -> DoencaCronica:
        """Fechar + criar novo numa só unidade: insere `nova` (flush para
        obter o id), fecha `antiga` apontando para ela e persiste junto.
        Com commit=False tudo fica só em flush (atômico com o chamador)."""
        db.session.add(nova)
        db.session.flush()
        antiga.encerrado_em = datetime.now(timezone.utc)
        antiga.encerrado_por = encerrado_por
        antiga.id_atendimento_encerramento = id_atendimento_encerramento
        antiga.id_substituida_por = nova.id
        db.session.add(antiga)
        self._persistir(commit)
        return nova

    # ------------------------------------------------------- estatísticas
    # --- F1: Doenças crônicas mais comuns na base ---
    def top_cid_ativas(self, id_empresa: int, limite: int = 10) -> list:
        """Ranking de codigo_cid10 com status='ativa' entre os pacientes da
        empresa. Conta só linhas VIGENTES e não removidas: uma linha
        encerrada por revisão (ex.: ativa -> em-remissao) continua com
        status='ativa' na linha antiga e inflaria o ranking.

        Retorna: [{"codigo_cid10": "I10", "descricao_cid10": "Hipertensão", "total": 214}, ...]
        """
        linhas = (
            db.session.query(
                DoencaCronica.codigo_cid10.label("codigo"),
                DoencaCronica.descricao_cid10.label("descricao"),
                func.count(DoencaCronica.id).label("total"),
            )
            .join(Paciente, DoencaCronica.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(DoencaCronica.status == "ativa")
            .filter(DoencaCronica.deletado == False)
            .filter(DoencaCronica.encerrado_em.is_(None))
            .group_by(DoencaCronica.codigo_cid10, DoencaCronica.descricao_cid10)
            .order_by(func.count(DoencaCronica.id).desc())
            .limit(limite)
            .all()
        )
        return [
            {"codigo_cid10": linha.codigo, "descricao_cid10": linha.descricao, "total": linha.total}
            for linha in linhas
        ]