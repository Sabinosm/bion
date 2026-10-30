"""repository.py

Acesso a dados dos registros clínicos coletados durante um Atendimento:
coleta clínica, sinais vitais, input de protocolo e o envio à IA (OutputBion).

A transação segue o padrão dos demais repositórios: salvar, confirmar e
desfazer; com commit desligado só se faz flush, para o service compor várias
escritas numa única transação. Nada é apagado fisicamente: a remoção levanta
NotImplementedError. O input de protocolo e o envio à IA são insert-only, e o
vigente é sempre o último registrado.
"""

from typing import Optional, List, Iterable, Set

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import ColetaClinica, SinalVital, InputProtocolo, LoincSinalVital
from src.models.protocolos.output_bion import OutputBion


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
        """Lista as ColetaClinica de um Atendimento, a mais recente primeiro."""
        return (
            ColetaClinica.query
            .filter_by(id_atendimento=id_atendimento)
            .order_by(ColetaClinica.id.desc())
            .all()
        )

    def find_ultima_do_atendimento(self, id_atendimento: int) -> Optional[ColetaClinica]:
        """A coleta vigente: a de maior id (última inserida) no atendimento."""
        return (
            ColetaClinica.query
            .filter_by(id_atendimento=id_atendimento)
            .order_by(ColetaClinica.id.desc())
            .first()
        )

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
        """Lista os InputProtocolo de uma ColetaClinica, o mais recente primeiro."""
        return (
            InputProtocolo.query
            .filter_by(id_coleta_clinica=id_coleta_clinica)
            .order_by(InputProtocolo.id.desc())
            .all()
        )

    def find_ultimo_do_atendimento(self, id_atendimento: int) -> Optional[InputProtocolo]:
        """O input vigente do atendimento: o último inserido, em qualquer
        coleta dele (insert-only, o último vale)."""
        return (
            InputProtocolo.query
            .join(ColetaClinica, InputProtocolo.id_coleta_clinica == ColetaClinica.id)
            .filter(ColetaClinica.id_atendimento == id_atendimento)
            .order_by(InputProtocolo.id.desc())
            .first()
        )

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


class OutputBionRepository(IRepository[OutputBion]):
    """Cada linha é um ENVIO à IA (criada antes da chamada). Só o último envio
    do atendimento é válido; os anteriores ficam (insert-only)."""

    def confirmar(self, commit: bool = True) -> None:
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    def find_by_id(self, id: int) -> Optional[OutputBion]:
        return db.session.get(OutputBion, id)

    def find_ultimo_do_atendimento(self, id_atendimento: int) -> Optional[OutputBion]:
        """O envio vigente do atendimento (criado_em desc, id desc)."""
        return (
            OutputBion.query
            .filter_by(id_atendimento=id_atendimento)
            .order_by(OutputBion.criado_em.desc(), OutputBion.id.desc())
            .first()
        )

    def find_all(self) -> List[OutputBion]:
        return OutputBion.query.all()

    def save(self, entity: OutputBion, commit: bool = True) -> OutputBion:
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError("OutputBion não é apagado fisicamente.")
