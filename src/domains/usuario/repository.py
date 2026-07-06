from typing import Optional, List

from src.database import db
from src.core.interfaces import IRepository
from src.database.usuarios import Usuario


class UsuarioRepository(IRepository[Usuario]):

    def find_by_id(self, id: int) -> Optional[Usuario]:
        return db.session.get(Usuario, id)

    def find_by_uuid(self, uuid: str) -> Optional[Usuario]:
        return Usuario.query.filter_by(uuid=uuid).first()

    def find_by_login(self, login: str) -> Optional[Usuario]:
        return Usuario.query.filter_by(user_login=login, status="ativo").first()

    def find_by_cpf_hash(self, cpf_hash: str) -> Optional[Usuario]:
        """Busca por HMAC-SHA256 do CPF (índice determinístico); ver nota em
        src/domains/paciente/repositories.py sobre por que não se pode
        buscar por igualdade do valor cifrado com AES-256-GCM."""
        return Usuario.query.filter_by(cpf_hash=cpf_hash).first()

    def find_by_email(self, email: str) -> Optional[Usuario]:
        return Usuario.query.filter_by(email=email).first()

    def save(self, entity: Usuario) -> Usuario:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        u = self.find_by_id(id)
        if not u:
            return False
        db.session.delete(u)
        db.session.commit()
        return True

    def find_all(self) -> List[Usuario]:
        return Usuario.query.all()

    def find_por_empresa(self, empresa_id: int) -> List[Usuario]:
        return Usuario.query.filter_by(id_empresa=empresa_id).all()

    