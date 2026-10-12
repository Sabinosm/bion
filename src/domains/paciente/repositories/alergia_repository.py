from typing import Optional, List
from datetime import datetime, timezone

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (Alergia, Paciente)



class AlergiaRepository(IRepository[Alergia]):
    """Toda leitura "normal" (find_by_id, find_by_uuid, find_por_paciente
    e as estatísticas abaixo) filtra `deletado == False` por padrão --
    mesmo padrão de DoencaCronicaRepository. find_apagados é o único
    ponto de acesso a registros soft-deletados."""

    def find_by_id(self, id: int) -> Optional[Alergia]:
        return (
            Alergia.query
            .filter(Alergia.id == id, Alergia.deletado == False)
            .first()
        )

    def find_by_uuid(self, uuid: str) -> Optional[Alergia]:
        return (
            Alergia.query
            .filter(Alergia.uuid == uuid, Alergia.deletado == False)
            .first()
        )

    def find_by_uuid_incluindo_deletados(self, uuid: str) -> Optional[Alergia]:
        """Busca sem filtrar deletado: distingue 'não existe' de 'está removida'."""
        return Alergia.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Alergia]:
        return (
            Alergia.query
            .filter(Alergia.id_paciente == id_paciente, Alergia.deletado == False)
            .order_by(Alergia.criado_em, Alergia.id)
            .all()
        )

    def find_ativa_por_substancia(self, id_paciente: int, substancia: str) -> Optional[Alergia]:
        """Alergia ATIVA do paciente com a mesma substância (barra duplicata).
        Comparação case-insensitive via lower(); a insensibilidade a acento
        depende da collation da coluna (utf8mb4_*_ci já ignora acento)."""
        from sqlalchemy import func
        return (
            Alergia.query
            .filter(Alergia.id_paciente == id_paciente,
                    Alergia.deletado == False,
                    func.lower(Alergia.substancia) == substancia.strip().lower())
            .first()
        )

    def find_apagados(self, id_paciente: Optional[int] = None) -> List[Alergia]:
        """Único ponto de acesso a alergias soft-deletadas (auditoria/admin)."""
        query = Alergia.query.filter(Alergia.deletado == True)
        if id_paciente is not None:
            query = query.filter(Alergia.id_paciente == id_paciente)
        return query.all()

    # ----------------------------------------------------------- escrita
    # commit=True: commit (rota granular). commit=False: só flush, para
    # compor operação atômica (acao_sensivel, rota agregada do binário).
    def _persistir(self, commit: bool) -> None:
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def save(self, entity: Alergia, commit: bool = True) -> Alergia:
        db.session.add(entity)
        self._persistir(commit)
        return entity

    def rollback(self) -> None:
        db.session.rollback()

    def delete(self, id: int) -> bool:
        raise NotImplementedError("Alergia não é apagada fisicamente; use soft_delete.")

    def delete_by_uuid(self, uuid: str) -> bool:
        raise NotImplementedError("Alergia não é apagada fisicamente; use soft_delete.")

    def soft_delete(self, entity: Alergia, motivo: str, observacoes_delete: Optional[str] = None,
                    deletado_por: Optional[int] = None,
                    id_atendimento_delecao: Optional[int] = None,
                    commit: bool = True) -> Alergia:
        """Marca como removida (e quem/qual atendimento) sem apagar a linha
        nem as reações."""
        entity.deletado = True
        entity.deletado_em = datetime.now(timezone.utc)
        entity.motivo_delete = motivo
        entity.observacoes_delete = observacoes_delete
        entity.deletado_por = deletado_por
        entity.id_atendimento_delecao = id_atendimento_delecao
        return self.save(entity, commit=commit)

    def restaurar(self, entity: Alergia, commit: bool = True) -> Alergia:
        """Reverte um soft delete (limpa os campos de remoção; o log de
        auditoria da rota guarda quem restaurou)."""
        entity.deletado = False
        entity.deletado_em = None
        entity.motivo_delete = None
        entity.observacoes_delete = None
        entity.deletado_por = None
        entity.id_atendimento_delecao = None
        return self.save(entity, commit=commit)

    # --- A2/E2/F4/D2: estatísticas ---
    # REMOVIDO: tempo_medio_por_tipo, atendimentos_por_status e
    # tempo_medio_por_tipo_periodo chamavam self.repo.xxx() -- código
    # de outra camada (service) colado aqui por engano; repository não
    # tem self.repo. Se essas estatísticas ainda são necessárias,
    # pertencem a AtendimentoRepository/Service (domínio diferente de
    # Alergia), não aqui -- me avisa que endereçamos separado.

    # --- F4: Gravidade geral das reações alérgicas (sem filtro por substância) ---
    def gravidade_geral(self, id_empresa: int) -> dict:
        """Mesma lógica de gravidade_por_substancia, mas sem o filtro
        WHERE substancia=... -- visão agregada de todas as reações da
        empresa, não drill-down de 1 substância específica. Filtra
        Alergia.deletado == False -- reação de alergia soft-deletada
        não deve entrar na estatística.

        Retorna: {"leve": 30, "moderada": 45, "grave": 9}
        """
        from sqlalchemy import func
        from src.models.pacientes.reacao_alergia import ReacaoAlergia

        linhas = (
            db.session.query(
                    ReacaoAlergia.gravidade.label("gravidade"),
                    func.count(ReacaoAlergia.id).label("total"),
                )
                .join(Alergia, ReacaoAlergia.id_alergia == Alergia.id)
                .join(Paciente, Alergia.id_paciente == Paciente.id)
                .filter(Paciente.id_empresa == id_empresa)
                .filter(Alergia.deletado == False)
                .group_by(ReacaoAlergia.gravidade)
                .all()
        )
        return {linha.gravidade: linha.total for linha in linhas}
    
    
    # --- D2: Alergias mais reportadas (por substância) ---
    def top_substancias(self, id_empresa: int, limite: int = 10) -> List[dict]:
        """Substâncias alergênicas mais reportadas entre os pacientes da
        empresa, com contagem de casos. Filtra deletado == False --
        alergia removida não deve inflar o ranking.
 
        Retorna lista de dicts, ordenada do mais frequente pro menos:
        [{"substancia": "Dipirona", "total": 18}, ...]
        """
        from sqlalchemy import func
 
        linhas = (
            db.session.query(
                Alergia.substancia.label("substancia"),
                func.count(Alergia.id).label("total"),
            )
            .join(Paciente, Alergia.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(Alergia.deletado == False)
            .group_by(Alergia.substancia)
            .order_by(func.count(Alergia.id).desc())
            .limit(limite)
            .all()
        )
        return [{"substancia": linha.substancia, "total": linha.total} for linha in linhas]
 
    # --- D2 (detalhe): gravidade das reações por substância ---
    def gravidade_por_substancia(self, id_empresa: int, substancia: str) -> dict:
        """Distribuição de gravidade (leve/moderada/grave) das reações
        registradas para uma substância específica -- usado como
        drill-down quando o usuário clica numa barra do ranking D2.
        Filtra deletado == False pelo mesmo motivo das estatísticas
        acima.
 
        Retorna dict, ex: {"leve": 5, "moderada": 10, "grave": 3}
        """
        from sqlalchemy import func
        from src.models.pacientes.reacao_alergia import ReacaoAlergia
 
        linhas = (
            db.session.query(
                ReacaoAlergia.gravidade.label("gravidade"),
                func.count(ReacaoAlergia.id).label("total"),
            )
            .join(Alergia, ReacaoAlergia.id_alergia == Alergia.id)
            .join(Paciente, Alergia.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(Alergia.substancia == substancia)
            .filter(Alergia.deletado == False)
            .group_by(ReacaoAlergia.gravidade)
            .all()
        )
        return {linha.gravidade: linha.total for linha in linhas}