"""input_protocolo_execucao_repository.py

Acesso a dados das execuções de protocolo (InputProtocoloExecucao). Grava e
consulta o resultado de qualquer execução, independente da família do
protocolo (NEWS2, composto, futuros).
"""
from typing import Optional

from src.core.interfaces import IRepository
from src.models import db
from src.models.clinico import InputProtocoloExecucao


class InputProtocoloExecucaoRepository(IRepository[InputProtocoloExecucao]):

    def find_by_id(self, id: int) -> Optional[InputProtocoloExecucao]:
        return db.session.get(InputProtocoloExecucao, id)

    def find_por_input_e_protocolo(
        self, id_input: int, id_protocolo_catalogo: int
    ) -> Optional[InputProtocoloExecucao]:
        """Busca a execução de um protocolo sobre um input.

        A UNIQUE KEY `uq_input_protocolo` impede duas execuções do mesmo
        protocolo sobre o mesmo input; esta consulta permite checar antes de
        salvar e devolver erro de negócio em vez de estourar IntegrityError.
        """
        return InputProtocoloExecucao.query.filter_by(
            id_input=id_input, id_protocolo_catalogo=id_protocolo_catalogo
        ).first()

    def find_por_input(self, id_input: int) -> list[InputProtocoloExecucao]:
        """Lista as execuções de um input, da mais antiga para a mais recente."""
        return (
            InputProtocoloExecucao.query
            .filter_by(id_input=id_input)
            .order_by(InputProtocoloExecucao.id)
            .all()
        )

    def save(self, entity: InputProtocoloExecucao, commit: bool = True) -> InputProtocoloExecucao:
        """Persiste a execução. Com `commit=False` apenas faz flush, deixando a
        transação com o chamador."""
        db.session.add(entity)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return entity

    def delete(self, id: int):
        raise NotImplementedError("Execuções de protocolo não são removidas por este repositório.")

    def find_by_uuid(self, uuid: str):
        raise NotImplementedError("InputProtocoloExecucao não é consultada por UUID.")
