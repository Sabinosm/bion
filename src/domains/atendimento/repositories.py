"""
Repositorios do dominio Atendimento (Consultas e Triagem): Consulta,
Atendimento, ColetaClinica, SinalVital, InputProtocolo, ResultadoPrescricao,
Prescricao, PrescricaoExame. Um arquivo unico (repositories.py, plural,
conforme caminhos.md) para o "dominio de Consultas e Triagem", ja que
todas essas entidades vivem dentro do ciclo de vida de uma Consulta.
"""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import (
    Consulta, Atendimento, ColetaClinica, SinalVital, InputProtocolo,
    ResultadoPrescricao, Prescricao, PrescricaoExame,
)

from src.models.clinico.prescricao_exame import PrescricaoExame



class ConsultaRepository(IRepository[Consulta]):

    def find_by_id(self, id: int) -> Optional[Consulta]:
        return db.session.get(Consulta, id)

    def find_by_uuid(self, uuid: str) -> Optional[Consulta]:
        return Consulta.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Consulta]:
        return Consulta.query.filter_by(id_paciente=id_paciente).order_by(
            Consulta.data_hora_inicio.desc()).all()

    def find_abertas(self) -> List[Consulta]:
        return Consulta.query.filter(Consulta.status_consulta != "encerrada").all()

    def save(self, entity: Consulta) -> Consulta:
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

    def find_all(self) -> List[Consulta]:
        return Consulta.query.all()


class AtendimentoRepository(IRepository[Atendimento]):

    def find_by_id(self, id: int) -> Optional[Atendimento]:
        return db.session.get(Atendimento, id)

    def find_by_uuid(self, uuid: str) -> Optional[Atendimento]:
        return Atendimento.query.filter_by(uuid=uuid).first()

    def find_por_consulta(self, id_consulta: int) -> List[Atendimento]:
        return Atendimento.query.filter_by(id_consulta=id_consulta).order_by(
            Atendimento.data_hora_inicio.asc()).all()

    def find_ultimo_por_tipo(self, id_consulta: int, tipo_atendimento: str) -> Optional[Atendimento]:
        return (
            Atendimento.query
            .filter_by(id_consulta=id_consulta, tipo_atendimento=tipo_atendimento)
            .order_by(Atendimento.data_hora_inicio.desc())
            .first()
        )

    def save(self, entity: Atendimento) -> Atendimento:
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

    def find_all(self) -> List[Atendimento]:
        return Atendimento.query.all()


class ColetaClinicaRepository(IRepository[ColetaClinica]):

    def find_by_id(self, id: int) -> Optional[ColetaClinica]:
        return db.session.get(ColetaClinica, id)

    def find_by_uuid(self, uuid: str) -> Optional[ColetaClinica]:
        return ColetaClinica.query.filter_by(uuid=uuid).first()

    def find_por_atendimento(self, id_atendimento: int) -> List[ColetaClinica]:
        return ColetaClinica.query.filter_by(id_atendimento=id_atendimento).all()

    def save(self, entity: ColetaClinica) -> ColetaClinica:
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

    def find_all(self) -> List[ColetaClinica]:
        return ColetaClinica.query.all()


class SinalVitalRepository(IRepository[SinalVital]):

    def find_by_id(self, id: int) -> Optional[SinalVital]:
        return db.session.get(SinalVital, id)

    def find_by_uuid(self, uuid: str) -> Optional[SinalVital]:
        return SinalVital.query.filter_by(uuid=uuid).first()

    def find_por_atendimento(self, id_atendimento: int) -> List[SinalVital]:
        return SinalVital.query.filter_by(id_atendimento=id_atendimento).order_by(
            SinalVital.data_hora_medicao.desc()).all()

    def save(self, entity: SinalVital) -> SinalVital:
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

    def find_all(self) -> List[SinalVital]:
        return SinalVital.query.all()


class InputProtocoloRepository(IRepository[InputProtocolo]):

    def find_by_id(self, id: int) -> Optional[InputProtocolo]:
        return db.session.get(InputProtocolo, id)

    def find_by_uuid(self, uuid: str) -> Optional[InputProtocolo]:
        return InputProtocolo.query.filter_by(uuid=uuid).first()

    def find_por_coleta(self, id_coleta_clinica: int) -> List[InputProtocolo]:
        return InputProtocolo.query.filter_by(id_coleta_clinica=id_coleta_clinica).all()

    def save(self, entity: InputProtocolo) -> InputProtocolo:
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

    def find_all(self) -> List[InputProtocolo]:
        return InputProtocolo.query.all()


class ResultadoPrescricaoRepository(IRepository[ResultadoPrescricao]):

    def find_by_id(self, id: int) -> Optional[ResultadoPrescricao]:
        return db.session.get(ResultadoPrescricao, id)

    def find_by_uuid(self, uuid: str) -> Optional[ResultadoPrescricao]:
        return ResultadoPrescricao.query.filter_by(uuid=uuid).first()

    def find_por_atendimento(self, id_atendimento: int) -> List[ResultadoPrescricao]:
        return ResultadoPrescricao.query.filter_by(id_atendimento=id_atendimento).all()

    def save(self, entity: ResultadoPrescricao) -> ResultadoPrescricao:
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

    def find_all(self) -> List[ResultadoPrescricao]:
        return ResultadoPrescricao.query.all()


class PrescricaoRepository(IRepository[Prescricao]):

    def find_by_id(self, id: int) -> Optional[Prescricao]:
        return db.session.get(Prescricao, id)

    def find_by_uuid(self, uuid: str) -> Optional[Prescricao]:
        return None  # Prescricao não tem uuid próprio no schema original

    def find_por_resultado(self, id_resultado_prescricao: int) -> List[Prescricao]:
        return Prescricao.query.filter_by(id_resultado_prescricao=id_resultado_prescricao).all()

    def save(self, entity: Prescricao) -> Prescricao:
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

    def find_all(self) -> List[Prescricao]:
        return Prescricao.query.all()


class PrescricaoExameRepository(IRepository[PrescricaoExame]):

    def find_by_id(self, id: int) -> Optional[PrescricaoExame]:
        return db.session.get(PrescricaoExame, id)

    def find_by_uuid(self, uuid: str) -> Optional[PrescricaoExame]:
        return PrescricaoExame.query.filter_by(uuid=uuid).first()

    def find_por_resultado(self, id_resultado: int) -> List[PrescricaoExame]:
        return PrescricaoExame.query.filter_by(id_resultado=id_resultado).all()

    def save(self, entity: PrescricaoExame) -> PrescricaoExame:
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

    def find_all(self) -> List[PrescricaoExame]:
        return PrescricaoExame.query.all()
