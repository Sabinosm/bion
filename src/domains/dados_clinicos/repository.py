"""
Repositórios do domínio Dados Clínicos: ColetaClinica, SinalVital e
InputProtocolo, coletados durante um Atendimento.
"""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import ColetaClinica, SinalVital, InputProtocolo


class ColetaClinicaRepository(IRepository[ColetaClinica]):
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

    def save(self, entity: ColetaClinica) -> ColetaClinica:
        """Persiste (insert ou update) uma ColetaClinica e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove uma ColetaClinica pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[ColetaClinica]:
        """Lista todas as ColetaClinica cadastradas, sem filtro."""
        return ColetaClinica.query.all()


class SinalVitalRepository(IRepository[SinalVital]):
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

    def save(self, entity: SinalVital) -> SinalVital:
        """Persiste (insert ou update) um SinalVital e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove um SinalVital pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

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
