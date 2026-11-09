"""obs_tipo_sanguineo_repository.py

Acesso a dados de ObservacaoTipoSanguineo. O tipo sanguíneo é INSERT-ONLY: não há
atualização, soft delete nem delete, e corrigir um valor é registrar uma nova
observação. A vigente é sempre a mais recente (data_registro desc, com o id
desempatando). A empresa da distribuição vem de Paciente.id_empresa.
commit=True confirma; commit=False só faz flush, para compor operações atômicas
(rota agregada do binário).
"""
from typing import Optional, List

from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import Paciente, ObservacaoTipoSanguineo


class ObservacaoTipoSanguineoRepository(IRepository[ObservacaoTipoSanguineo]):

    def find_by_id(self, id: int) -> Optional[ObservacaoTipoSanguineo]:
        return db.session.get(ObservacaoTipoSanguineo, id)

    def find_by_uuid(self, uuid: str) -> Optional[ObservacaoTipoSanguineo]:
        return ObservacaoTipoSanguineo.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[ObservacaoTipoSanguineo]:
        """Histórico completo, da mais recente para a mais antiga."""
        return (
            ObservacaoTipoSanguineo.query
            .filter_by(id_paciente=id_paciente)
            .order_by(ObservacaoTipoSanguineo.data_registro.desc(),
                      ObservacaoTipoSanguineo.id.desc())
            .all()
        )

    def find_mais_recente_por_paciente(self, id_paciente: int) -> Optional[ObservacaoTipoSanguineo]:
        """A observação vigente (None se nunca foi registrada)."""
        return (
            ObservacaoTipoSanguineo.query
            .filter_by(id_paciente=id_paciente)
            .order_by(ObservacaoTipoSanguineo.data_registro.desc(),
                      ObservacaoTipoSanguineo.id.desc())
            .first()
        )

    # ----------------------------------------------------------- escrita
    def confirmar(self, commit: bool = True) -> None:
        """commit=True: commita; commit=False: só flush (a transação segue aberta)."""
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    def save(self, entity: ObservacaoTipoSanguineo, commit: bool = True) -> ObservacaoTipoSanguineo:
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError(
            "Observação de tipo sanguíneo é insert-only; registre uma nova observação.")

    def delete_by_uuid(self, uuid: str) -> bool:
        raise NotImplementedError(
            "Observação de tipo sanguíneo é insert-only; registre uma nova observação.")

    # ------------------------------------------------------------ estatísticas
    def distribuicao_tipo_sanguineo(self, id_empresa: int) -> dict:
        """Distribuição por tipo, só com a observação VIGENTE de cada paciente.

        Vigente = maior id por paciente (insert-only: o id cresce com o tempo). Usar
        MAX(data_registro) empatava em inserções no mesmo instante e contava o paciente duas vezes.

        Retorna: {"O+": 120, "A+": 95, ...}
        """
        subq = (
            db.session.query(func.max(ObservacaoTipoSanguineo.id).label("max_id"))
            .group_by(ObservacaoTipoSanguineo.id_paciente)
            .subquery()
        )
        linhas = (
            db.session.query(
                ObservacaoTipoSanguineo.tipo_sanguineo.label("tipo"),
                func.count(ObservacaoTipoSanguineo.id).label("total"),
            )
            .join(subq, ObservacaoTipoSanguineo.id == subq.c.max_id)
            .join(Paciente, ObservacaoTipoSanguineo.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .group_by(ObservacaoTipoSanguineo.tipo_sanguineo)
            .all()
        )
        return {linha.tipo: linha.total for linha in linhas}
