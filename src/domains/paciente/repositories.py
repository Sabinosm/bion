"""
Repositorios do dominio Paciente (Paciente, dados pessoais, alergias,
doencas cronicas, medicamentos em uso e consentimento LGPD).

Um arquivo unico (repositories.py, plural, conforme caminhos.md) reunindo
todos os repositorios do dominio, ja que sao entidades satelites pequenas
e sempre acessadas no contexto de um Paciente.
"""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (
    Paciente, PacientePessoal, Alergia, DoencaCronica, MedicamentoEmUso, Consentimento,
)


class PacienteRepository(IRepository[Paciente]):

    def find_by_id(self, id: int) -> Optional[Paciente]:
        return db.session.get(Paciente, id)

    def find_by_uuid(self, uuid: str) -> Optional[Paciente]:
        return Paciente.query.filter_by(uuid=uuid).first()

    def find_por_cpf_hash(self, cpf_hash: str) -> Optional[Paciente]:
        """
        Busca por CPF via hash HMAC-SHA256 (determinístico), não pelo valor
        cifrado com AES-256-GCM. O AES usa nonce aleatório por chamada, então
        `aes_encrypt(mesmo_cpf)` nunca repete o mesmo ciphertext -- buscar
        por igualdade de ciphertext nunca encontraria o registro existente.
        O hash serve apenas como índice de busca; o valor exibível continua
        sendo o AES armazenado em `cpf`.
        """
        pessoal = PacientePessoal.query.filter_by(cpf_hash=cpf_hash).first()
        return pessoal.paciente if pessoal else None

    def save(self, entity: Paciente) -> Paciente:
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

    def find_all(self) -> List[Paciente]:
        return Paciente.query.all()


class AlergiaRepository(IRepository[Alergia]):

    def find_by_id(self, id: int) -> Optional[Alergia]:
        return db.session.get(Alergia, id)

    def find_by_uuid(self, uuid: str) -> Optional[Alergia]:
        return Alergia.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Alergia]:
        return Alergia.query.filter_by(id_paciente=id_paciente).all()

    def save(self, entity: Alergia) -> Alergia:
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


class DoencaCronicaRepository(IRepository[DoencaCronica]):

    def find_by_id(self, id: int) -> Optional[DoencaCronica]:
        return db.session.get(DoencaCronica, id)

    def find_by_uuid(self, uuid: str) -> Optional[DoencaCronica]:
        return DoencaCronica.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[DoencaCronica]:
        return DoencaCronica.query.filter_by(id_paciente=id_paciente).all()

    def save(self, entity: DoencaCronica) -> DoencaCronica:
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


class MedicamentoEmUsoRepository(IRepository[MedicamentoEmUso]):

    def find_by_id(self, id: int) -> Optional[MedicamentoEmUso]:
        return db.session.get(MedicamentoEmUso, id)

    def find_by_uuid(self, uuid: str) -> Optional[MedicamentoEmUso]:
        # MedicamentoEmUso nao tem uuid proprio no schema original (so id);
        # mantido por conformidade com IRepository, mas nao usado nas rotas.
        return None

    def find_por_paciente(self, id_paciente: int) -> List[MedicamentoEmUso]:
        return MedicamentoEmUso.query.filter_by(id_paciente=id_paciente).all()

    def save(self, entity: MedicamentoEmUso) -> MedicamentoEmUso:
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


class ConsentimentoRepository(IRepository[Consentimento]):

    def find_by_id(self, id: int) -> Optional[Consentimento]:
        return db.session.get(Consentimento, id)

    def find_by_uuid(self, uuid: str) -> Optional[Consentimento]:
        return Consentimento.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Consentimento]:
        return Consentimento.query.filter_by(id_paciente=id_paciente).all()

    def find_ativo_por_paciente(self, id_paciente: int) -> Optional[Consentimento]:
        return Consentimento.query.filter_by(id_paciente=id_paciente, status="ativo").first()

    def save(self, entity: Consentimento) -> Consentimento:
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
