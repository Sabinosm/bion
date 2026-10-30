"""repository.py

Acesso a dados da conduta de enfermagem. O registro é INSERT-ONLY: não existe
atualização e a remoção levanta NotImplementedError, porque uma correção é uma
nova conduta.

A conduta não tem empresa própria: a posse vem de Atendimento -> Consulta, e o
service a valida antes de chamar as buscas por atendimento e por consulta (a
listagem geral é a exceção e filtra a empresa aqui mesmo). Com commit desligado
a gravação só faz flush, para o controller comitar junto com o log de auditoria.
"""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import Atendimento, Consulta
from src.models.clinico.conduta_enfermagem import CondutaEnfermagem


class CondutaEnfermagemRepository(IRepository[CondutaEnfermagem]):

    def confirmar(self, commit: bool = True) -> None:
        """Commit, ou só flush se o chamador vai comitar depois."""
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        """Desfaz a transação corrente."""
        db.session.rollback()

    def find_by_id(self, id: int) -> Optional[CondutaEnfermagem]:
        """Busca pela chave primária, SEM filtro de empresa: só para ids já validados."""
        return db.session.get(CondutaEnfermagem, id)

    def find_by_uuid(self, uuid: str):
        raise NotImplementedError("CondutaEnfermagem não é consultada por UUID.")

    def find_all(self, id_empresa: int) -> List[CondutaEnfermagem]:
        """Lista as condutas da empresa, da mais recente para a mais antiga."""
        return (
            CondutaEnfermagem.query
            .join(Atendimento, CondutaEnfermagem.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Consulta.id_empresa == id_empresa)
            .order_by(CondutaEnfermagem.criado_em.desc(), CondutaEnfermagem.id.desc())
            .all()
        )

    def find_por_atendimento(self, id_atendimento: int) -> List[CondutaEnfermagem]:
        """Lista as condutas de um Atendimento em ordem cronológica crescente."""
        return (
            CondutaEnfermagem.query
            .filter_by(id_atendimento=id_atendimento)
            .order_by(CondutaEnfermagem.criado_em.asc(), CondutaEnfermagem.id.asc())
            .all()
        )

    def find_por_consulta(self, id_consulta: int) -> List[CondutaEnfermagem]:
        """Lista as condutas de todos os Atendimentos de uma Consulta, em ordem cronológica crescente."""
        return (
            CondutaEnfermagem.query
            .join(Atendimento, CondutaEnfermagem.id_atendimento == Atendimento.id)
            .filter(Atendimento.id_consulta == id_consulta)
            .order_by(CondutaEnfermagem.criado_em.asc(), CondutaEnfermagem.id.asc())
            .all()
        )

    def find_protocolo_por_uuid(self, uuid: str):
        """Busca o ProtocoloCatalogo pelo UUID público (o catálogo é global, sem filtro de empresa)."""
        from src.models.protocolos import ProtocoloCatalogo
        return ProtocoloCatalogo.query.filter_by(uuid=uuid).first()

    def save(self, entity: CondutaEnfermagem, commit: bool = True) -> CondutaEnfermagem:
        """Insere uma conduta. commit=False só faz flush."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        """Não existe: conduta é registro clínico insert-only e não pode ser apagada."""
        raise NotImplementedError(
            "Conduta de enfermagem é insert-only; registre uma nova conduta para corrigir."
        )
