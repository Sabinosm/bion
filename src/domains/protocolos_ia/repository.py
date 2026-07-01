from typing import Optional, List

from src.database import db
from src.core.interfaces import IRepository
from src.database.protocolos import (
    ProtocoloCatalogo, CatalogoFluxogramasMts, CatalogoModulos, OutputBion,
)
from src.database.clinico import Consulta, Atendimento, ColetaClinica, InputProtocolo


class ProtocoloCatalogoRepository(IRepository[ProtocoloCatalogo]):

    def find_by_id(self, id: int) -> Optional[ProtocoloCatalogo]:
        return db.session.get(ProtocoloCatalogo, id)

    def find_by_uuid(self, uuid: str) -> Optional[ProtocoloCatalogo]:
        return ProtocoloCatalogo.query.filter_by(uuid=uuid).first()

    def find_by_sigla(self, sigla: str) -> Optional[ProtocoloCatalogo]:
        return ProtocoloCatalogo.query.filter_by(sigla=sigla).first()

    def save(self, entity: ProtocoloCatalogo) -> ProtocoloCatalogo:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[ProtocoloCatalogo]:
        return ProtocoloCatalogo.query.all()


class OutputBionRepository(IRepository[OutputBion]):

    def find_by_id(self, id: int) -> Optional[OutputBion]:
        return db.session.get(OutputBion, id)

    def find_by_uuid(self, uuid: str) -> Optional[OutputBion]:
        return OutputBion.query.filter_by(uuid=uuid).first()

    def save(self, entity: OutputBion) -> OutputBion:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[OutputBion]:
        return OutputBion.query.all()

    def find_output_triagem_da_consulta(self, uuid_consulta: str) -> Optional[OutputBion]:
        """
        Navega Consulta -> Atendimento(tipo=triagem) -> ColetaClinica ->
        InputProtocolo -> OutputBion mais recente. Usado pela tela de
        avaliacao medica para reaproveitar o resultado ja calculado pela
        IA na triagem, sem reprocessar.
        """
        consulta = Consulta.query.filter_by(uuid=uuid_consulta).first()
        if not consulta:
            return None

        atendimento_triagem = (
            Atendimento.query
            .filter_by(id_consulta=consulta.id, tipo_atendimento="triagem")
            .order_by(Atendimento.data_hora_inicio.desc())
            .first()
        )
        if not atendimento_triagem:
            return None

        coleta = (
            ColetaClinica.query
            .filter_by(id_atendimento=atendimento_triagem.id)
            .order_by(ColetaClinica.id.desc())
            .first()
        )
        if not coleta:
            return None

        input_protocolo = (
            InputProtocolo.query
            .filter_by(id_coleta_clinica=coleta.id)
            .order_by(InputProtocolo.id.desc())
            .first()
        )
        if not input_protocolo or not input_protocolo.outputs:
            return None

        return sorted(input_protocolo.outputs, key=lambda o: o.criado_em, reverse=True)[0]


class CatalogoFluxogramasMtsRepository(IRepository[CatalogoFluxogramasMts]):

    def find_by_id(self, id: int) -> Optional[CatalogoFluxogramasMts]:
        return db.session.get(CatalogoFluxogramasMts, id)

    def find_by_uuid(self, uuid: str) -> Optional[CatalogoFluxogramasMts]:
        return CatalogoFluxogramasMts.query.filter_by(uuid=uuid).first()

    def save(self, entity: CatalogoFluxogramasMts) -> CatalogoFluxogramasMts:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[CatalogoFluxogramasMts]:
        return CatalogoFluxogramasMts.query.all()


class CatalogoModulosRepository(IRepository[CatalogoModulos]):

    def find_by_id(self, id: int) -> Optional[CatalogoModulos]:
        return db.session.get(CatalogoModulos, id)

    def find_by_uuid(self, uuid: str) -> Optional[CatalogoModulos]:
        return CatalogoModulos.query.filter_by(uuid=uuid).first()

    def save(self, entity: CatalogoModulos) -> CatalogoModulos:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[CatalogoModulos]:
        return CatalogoModulos.query.all()
