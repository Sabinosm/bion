"""
Repositórios do domínio Dados Clínicos: ColetaClinica, SinalVital e
InputProtocolo, coletados durante um Atendimento.

TRANSAÇÃO: save(entity, commit=True) / confirmar(commit) / rollback(), no
mesmo padrão dos demais repositórios. commit=False só faz flush, para o
service compor várias escritas numa transação.

Nada é apagado fisicamente: delete() levanta NotImplementedError.
"""

from typing import Optional, List, Iterable, Set

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import ColetaClinica, SinalVital, InputProtocolo, LoincSinalVital


class ColetaClinicaRepository(IRepository[ColetaClinica]):
    """Encapsula todo acesso a dados de ColetaClinica via SQLAlchemy."""

    # ------------------------------------------------------------ transação
    def confirmar(self, commit: bool = True) -> None:
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    # ---------------------------------------------------------------- leitura
    def find_by_id(self, id: int) -> Optional[ColetaClinica]:
        """Busca uma ColetaClinica pelo ID interno (chave primária)."""
        return db.session.get(ColetaClinica, id)

    def find_by_uuid(self, uuid: str) -> Optional[ColetaClinica]:
        """Busca uma ColetaClinica pelo UUID público (sem tenant). Para rotas
        use find_by_uuid_do_atendimento, que amarra a coleta ao atendimento
        já validado pelo guard (e portanto ao tenant)."""
        return ColetaClinica.query.filter_by(uuid=uuid).first()

    def find_by_uuid_do_atendimento(self, uuid: str, id_atendimento: int) -> Optional[ColetaClinica]:
        """Coleta pelo UUID, SÓ se pertencer a este atendimento. 'Não existe'
        e 'é de outro atendimento' = None."""
        return ColetaClinica.query.filter_by(uuid=uuid, id_atendimento=id_atendimento).first()

    def find_por_atendimento(self, id_atendimento: int) -> List[ColetaClinica]:
        """Lista as ColetaClinica associadas a um Atendimento."""
        return ColetaClinica.query.filter_by(id_atendimento=id_atendimento).all()

    def find_all(self) -> List[ColetaClinica]:
        """Lista todas as ColetaClinica cadastradas, sem filtro (sem tenant)."""
        return ColetaClinica.query.all()

    # --------------------------------------------------------------- escrita
    def save(self, entity: ColetaClinica, commit: bool = True) -> ColetaClinica:
        """Persiste (insert ou update) uma ColetaClinica."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError("ColetaClinica não é apagada fisicamente.")


class SinalVitalRepository(IRepository[SinalVital]):
    """Encapsula todo acesso a dados de SinalVital via SQLAlchemy."""

    # ------------------------------------------------------------ transação
    def confirmar(self, commit: bool = True) -> None:
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    # ---------------------------------------------------------------- leitura
    def find_by_id(self, id: int) -> Optional[SinalVital]:
        """Busca um SinalVital pelo ID interno (chave primária)."""
        return db.session.get(SinalVital, id)

    def find_by_uuid(self, uuid: str) -> Optional[SinalVital]:
        """Busca um SinalVital pelo UUID público exposto na API (sem tenant)."""
        return SinalVital.query.filter_by(uuid=uuid).first()

    def find_por_atendimento(self, id_atendimento: int) -> List[SinalVital]:
        """Lista os SinalVital de um Atendimento, mais recente primeiro."""
        return (
            SinalVital.query
            .filter_by(id_atendimento=id_atendimento)
            .order_by(SinalVital.data_hora_medicao.desc())
            .all()
        )

    def find_all(self) -> List[SinalVital]:
        """Lista todos os SinalVital cadastrados, sem filtro (sem tenant)."""
        return SinalVital.query.all()

    def tipos_loinc_existentes(self, tipos: Iterable[str]) -> Set[str]:
        """Dos `tipos` informados, os que existem na tabela de referência
        loinc_sinal_vital (uma consulta só)."""
        tipos = list(tipos)
        if not tipos:
            return set()
        linhas = (
            db.session.query(LoincSinalVital.tipo_parametro)
            .filter(LoincSinalVital.tipo_parametro.in_(tipos))
            .all()
        )
        return {linha[0] for linha in linhas}

    # --------------------------------------------------------------- escrita
    def save(self, entity: SinalVital, commit: bool = True) -> SinalVital:
        """Persiste (insert ou update) um SinalVital."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError("SinalVital não é apagado fisicamente.")


class InputProtocoloRepository(IRepository[InputProtocolo]):
    """Encapsula todo acesso a dados de InputProtocolo via SQLAlchemy."""

    # ------------------------------------------------------------ transação
    def confirmar(self, commit: bool = True) -> None:
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    # ---------------------------------------------------------------- leitura
    def find_by_id(self, id: int) -> Optional[InputProtocolo]:
        """Busca um InputProtocolo pelo ID interno (chave primária)."""
        return db.session.get(InputProtocolo, id)

    def find_by_uuid(self, uuid: str) -> Optional[InputProtocolo]:
        """Busca um InputProtocolo pelo UUID público exposto na API (sem tenant)."""
        return InputProtocolo.query.filter_by(uuid=uuid).first()

    def find_por_coleta(self, id_coleta_clinica: int) -> List[InputProtocolo]:
        """Lista os InputProtocolo associados a uma ColetaClinica."""
        return InputProtocolo.query.filter_by(id_coleta_clinica=id_coleta_clinica).all()

    def find_all(self) -> List[InputProtocolo]:
        """Lista todos os InputProtocolo cadastrados, sem filtro (sem tenant)."""
        return InputProtocolo.query.all()

    # --------------------------------------------------------------- escrita
    def save(self, entity: InputProtocolo, commit: bool = True) -> InputProtocolo:
        """Persiste (insert ou update) um InputProtocolo."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError("InputProtocolo não é apagado fisicamente.")