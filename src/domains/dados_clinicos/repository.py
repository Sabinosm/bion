"""
Repositórios do domínio Dados Clínicos: ColetaClinica, SinalVital e
InputProtocolo, coletados durante um Atendimento.

ALTERADO (Bloco 2): ColetaClinicaRepository e SinalVitalRepository seguem o
padrão transacional do PacienteRepository: save(entity, commit=True),
confirmar(commit) e rollback(); commit=False só faz flush. Nada é apagado
fisicamente: delete() levanta NotImplementedError.

InputProtocoloRepository NÃO mudou (próximo passo).
"""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import ColetaClinica, SinalVital, InputProtocolo


class _Transacao:
    """confirmar/rollback compartilhados (commit=False => só flush)."""

    def confirmar(self, commit: bool = True) -> None:
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()


class ColetaClinicaRepository(_Transacao, IRepository[ColetaClinica]):
    """Encapsula todo acesso a dados de ColetaClinica via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[ColetaClinica]:
        """Busca uma ColetaClinica pelo ID interno (chave primária)."""
        return db.session.get(ColetaClinica, id)

    def find_by_uuid(self, uuid: str) -> Optional[ColetaClinica]:
        """Busca uma ColetaClinica pelo UUID público exposto na API."""
        return ColetaClinica.query.filter_by(uuid=uuid).first()

    def find_por_atendimento(self, id_atendimento: int) -> List[ColetaClinica]:
        """Lista as ColetaClinica associadas a um Atendimento."""
        return ColetaClinica.query.filter_by(id_atendimento=id_atendimento).all()

    def save(self, entity: ColetaClinica, commit: bool = True) -> ColetaClinica:
        """Persiste uma ColetaClinica. commit=False só faz flush."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError(
            "ColetaClinica não é apagada fisicamente (exclusão lógica, quando houver)."
        )

    def find_all(self) -> List[ColetaClinica]:
        """Lista todas as ColetaClinica cadastradas, sem filtro."""
        return ColetaClinica.query.all()


class SinalVitalRepository(_Transacao, IRepository[SinalVital]):
    """Encapsula todo acesso a dados de SinalVital via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[SinalVital]:
        """Busca um SinalVital pelo ID interno (chave primária)."""
        return db.session.get(SinalVital, id)

    def find_by_uuid(self, uuid: str) -> Optional[SinalVital]:
        """Busca um SinalVital pelo UUID público exposto na API."""
        return SinalVital.query.filter_by(uuid=uuid).first()

    def find_por_atendimento(self, id_atendimento: int) -> List[SinalVital]:
        """Lista os SinalVital de um Atendimento, mais recente primeiro."""
        return (
            SinalVital.query
            .filter_by(id_atendimento=id_atendimento)
            .order_by(SinalVital.data_hora_medicao.desc())
            .all()
        )

    def save(self, entity: SinalVital, commit: bool = True) -> SinalVital:
        """Persiste um SinalVital. commit=False só faz flush."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError(
            "SinalVital não é apagado fisicamente (exclusão lógica, quando houver)."
        )

    def find_all(self) -> List[SinalVital]:
        """Lista todos os SinalVital cadastrados, sem filtro."""
        return SinalVital.query.all()


class InputProtocoloRepository(IRepository[InputProtocolo]):
    """Encapsula todo acesso a dados de InputProtocolo via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[InputProtocolo]:
        """Busca um InputProtocolo pelo ID interno (chave primária)."""
        return db.session.get(InputProtocolo, id)

    def find_by_uuid(self, uuid: str) -> Optional[InputProtocolo]:
        """Busca um InputProtocolo pelo UUID público exposto na API."""
        return InputProtocolo.query.filter_by(uuid=uuid).first()

    def find_por_coleta(self, id_coleta_clinica: int) -> List[InputProtocolo]:
        """Lista os InputProtocolo associados a uma ColetaClinica."""
        return InputProtocolo.query.filter_by(id_coleta_clinica=id_coleta_clinica).all()

    def save(self, entity: InputProtocolo) -> InputProtocolo:
        """Persiste (insert ou update) um InputProtocolo e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove um InputProtocolo pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[InputProtocolo]:
        """Lista todos os InputProtocolo cadastrados, sem filtro."""
        return InputProtocolo.query.all()