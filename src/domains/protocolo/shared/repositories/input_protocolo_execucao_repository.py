"""Repositório de persistência de InputProtocoloExecucao — grava o resultado
de qualquer execução de protocolo (NEWS2, MTS, futuros), independente da família."""

from typing import Optional

from src.models import db
from src.core.interfaces import IRepository
from src.models.protocolos import InputProtocoloExecucao


class InputProtocoloExecucaoRepository(IRepository[InputProtocoloExecucao]):

    def find_by_id(self, id: int) -> Optional[InputProtocoloExecucao]:
        return db.session.get(InputProtocoloExecucao, id)

    def find_por_input_e_protocolo(self, id_input: int, id_protocolo_catalogo: int) -> Optional[InputProtocoloExecucao]:
        """A UNIQUE KEY uq_input_protocolo impede duas execuções do mesmo
        protocolo sobre o mesmo input -- útil pra checar antes de tentar salvar
        e devolver erro de negócio em vez de estourar IntegrityError."""
        return InputProtocoloExecucao.query.filter_by(
            id_input=id_input, id_protocolo_catalogo=id_protocolo_catalogo
        ).first()

    def save(self, entity: InputProtocoloExecucao, commit: bool = True) -> InputProtocoloExecucao:
        db.session.add(entity)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return entity