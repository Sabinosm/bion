"""alergia_repository.py

Acesso a dados de Alergia (o registro da substância; as reações ficam em
ReacaoAlergia). Toda leitura "normal" filtra deletado == False, e
find_apagados é o único ponto de acesso a registros soft-deletados (mais a busca
que os inclui, usada para distinguir 404 de 409). Nada é apagado fisicamente:
a remoção é soft delete, com motivo, autor e atendimento da remoção.

A empresa das estatísticas vem de Paciente.id_empresa. commit=True confirma
(rota granular); commit=False só faz flush, para compor operações atômicas (ação
sensível, rota agregada do binário).
"""
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import Alergia, Paciente
from src.models.pacientes.reacao_alergia import ReacaoAlergia


class AlergiaRepository(IRepository[Alergia]):

    # ---------------------------------------------------------------- leitura
    def find_by_id(self, id: int) -> Optional[Alergia]:
        return Alergia.query.filter(Alergia.id == id, Alergia.deletado.is_(False)).first()

    def find_by_uuid(self, uuid: str) -> Optional[Alergia]:
        return Alergia.query.filter(Alergia.uuid == uuid, Alergia.deletado.is_(False)).first()

    def find_by_uuid_incluindo_deletados(self, uuid: str) -> Optional[Alergia]:
        """Busca sem filtrar deletado: distingue 'não existe' de 'está removida'."""
        return Alergia.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Alergia]:
        return (
            Alergia.query
            .filter(Alergia.id_paciente == id_paciente, Alergia.deletado.is_(False))
            .order_by(Alergia.criado_em, Alergia.id)
            .all()
        )

    def find_ativa_por_substancia(self, id_paciente: int, substancia: str) -> Optional[Alergia]:
        """Alergia ATIVA do paciente com a mesma substância (barra duplicata). A comparação ignora
        a caixa via lower(); a insensibilidade a acento depende da collation da coluna (as
        utf8mb4_*_ci já ignoram acento)."""
        return (
            Alergia.query
            .filter(Alergia.id_paciente == id_paciente,
                    Alergia.deletado.is_(False),
                    func.lower(Alergia.substancia) == substancia.strip().lower())
            .first()
        )

    def find_apagados(self, id_paciente: Optional[int] = None) -> List[Alergia]:
        """Único ponto de acesso a alergias soft-deletadas (auditoria/admin)."""
        query = Alergia.query.filter(Alergia.deletado.is_(True))
        if id_paciente is not None:
            query = query.filter(Alergia.id_paciente == id_paciente)
        return query.all()

    # ----------------------------------------------------------- escrita
    def confirmar(self, commit: bool = True) -> None:
        """commit=True: commita; commit=False: só flush (a transação segue aberta)."""
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    def save(self, entity: Alergia, commit: bool = True) -> Alergia:
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError("Alergia não é apagada fisicamente; use soft_delete.")

    def delete_by_uuid(self, uuid: str) -> bool:
        raise NotImplementedError("Alergia não é apagada fisicamente; use soft_delete.")

    def soft_delete(self, entity: Alergia, motivo: str, observacoes_delete: Optional[str] = None,
                    deletado_por: Optional[int] = None,
                    id_atendimento_delecao: Optional[int] = None,
                    commit: bool = True) -> Alergia:
        """Marca como removida (e quem/qual atendimento) sem apagar a linha nem as reações."""
        entity.deletado = True
        entity.deletado_em = datetime.now(timezone.utc)
        entity.motivo_delete = motivo
        entity.observacoes_delete = observacoes_delete
        entity.deletado_por = deletado_por
        entity.id_atendimento_delecao = id_atendimento_delecao
        return self.save(entity, commit=commit)

    def restaurar(self, entity: Alergia, commit: bool = True) -> Alergia:
        """Reverte um soft delete (limpa os campos de remoção; o log de auditoria da rota guarda
        quem restaurou)."""
        entity.deletado = False
        entity.deletado_em = None
        entity.motivo_delete = None
        entity.observacoes_delete = None
        entity.deletado_por = None
        entity.id_atendimento_delecao = None
        return self.save(entity, commit=commit)

    # ------------------------------------------------------------ estatísticas
    def gravidade_geral(self, id_empresa: int) -> dict:
        """Distribuição de gravidade das reações não removidas de todas as alergias não removidas da
        empresa (visão agregada, sem filtro por substância).

        Retorna: {"leve": 30, "moderada": 45, "grave": 9}
        """
        linhas = (
            db.session.query(
                ReacaoAlergia.gravidade.label("gravidade"),
                func.count(ReacaoAlergia.id).label("total"),
            )
            .join(Alergia, ReacaoAlergia.id_alergia == Alergia.id)
            .join(Paciente, Alergia.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(Alergia.deletado.is_(False))
            .filter(ReacaoAlergia.deletado.is_(False))
            .group_by(ReacaoAlergia.gravidade)
            .all()
        )
        return {linha.gravidade: linha.total for linha in linhas}

    def top_substancias(self, id_empresa: int, limite: int = 10) -> List[dict]:
        """Substâncias alergênicas mais reportadas entre os pacientes da empresa, com a contagem
        de casos. Alergia removida não infla o ranking.

        Retorna: [{"substancia": "Dipirona", "total": 18}, ...] do mais frequente ao menos.
        """
        linhas = (
            db.session.query(
                Alergia.substancia.label("substancia"),
                func.count(Alergia.id).label("total"),
            )
            .join(Paciente, Alergia.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(Alergia.deletado.is_(False))
            .group_by(Alergia.substancia)
            .order_by(func.count(Alergia.id).desc())
            .limit(limite)
            .all()
        )
        return [{"substancia": linha.substancia, "total": linha.total} for linha in linhas]

    def gravidade_por_substancia(self, id_empresa: int, substancia: str) -> dict:
        """Distribuição de gravidade (leve/moderada/grave) das reações não removidas de UMA
        substância: o detalhe do ranking de top_substancias, quando o usuário clica numa barra.

        Retorna: {"leve": 5, "moderada": 10, "grave": 3}
        """
        linhas = (
            db.session.query(
                ReacaoAlergia.gravidade.label("gravidade"),
                func.count(ReacaoAlergia.id).label("total"),
            )
            .join(Alergia, ReacaoAlergia.id_alergia == Alergia.id)
            .join(Paciente, Alergia.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(Alergia.substancia == substancia)
            .filter(Alergia.deletado.is_(False))
            .filter(ReacaoAlergia.deletado.is_(False))
            .group_by(ReacaoAlergia.gravidade)
            .all()
        )
        return {linha.gravidade: linha.total for linha in linhas}
