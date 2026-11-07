from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column("id_usuario", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_usuario",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"), nullable=False)
    google_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    nome_completo = db.Column(db.String(255), nullable=False)
    cpf = db.Column(db.String(500), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    telefone = db.Column(db.String(50))
    user_login = db.Column(db.String(100), unique=True)
    is_admin = db.Column("is_admin", db.Boolean, nullable=False, default=False)
    is_super_admin = db.Column("is_super_admin", db.Boolean, nullable=False, default=False)
    status = db.Column(db.Enum("ativo", "inativo", "pendente"), nullable=False, default="pendente")
    hash_senha = db.Column(db.String(255), nullable=True)
    senha_versao = db.Column("senha_versao", db.Integer, nullable=False, default=1)
    avatar_filename = db.Column(db.String(255), nullable=True)
    onboarding_pendente = db.Column(db.Boolean, default=True, nullable=False)
    ultimo_acesso = db.Column(db.DateTime(timezone=True))
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    cpf_hash = db.Column(db.String(255), nullable=False)

    empresa = db.relationship("Empresa", back_populates="usuarios")
    configuracao = db.relationship(
        "Configuracao", back_populates="usuario", uselist=False, cascade="all, delete-orphan"
    )
    papeis = db.relationship(
        "PapelProfissional", back_populates="usuario", cascade="all, delete-orphan"
    )

    def papel_ativo(self):
        return next((p for p in self.papeis if p.ativo), None)

    @property
    def funcao_clinica(self):
        papel = self.papel_ativo()
        return papel.tipo_papel if papel else None

    def is_medico(self):
        papel = self.papel_ativo()
        return bool(papel and papel.tipo_papel == "medico")

    def is_enfermeiro(self):
        papel = self.papel_ativo()
        return bool(papel and papel.tipo_papel == "enfermeiro")

    def _avatar_url(self):
        import os

        if not self.avatar_filename:
            return None
        supabase_url = os.environ.get("SUPABASE_URL", "")
        bucket = os.environ.get("SUPABASE_BUCKET", "avatares")
        return f"{supabase_url}/storage/v1/object/public/{bucket}/{self.avatar_filename}"

    def to_dict(self, incluir_sensiveis=False):
        papel = self.papel_ativo()
        d = {
            "uuid": self.uuid,
            "nome_completo": self.nome_completo,
            "email": self.email,
            "telefone": self.telefone,
            "user_login": self.user_login,
            "funcao_clinica": self.funcao_clinica,
            "is_admin": self.is_admin,
            "is_super_admin": self.is_super_admin,
            "status": self.status,
            "ultimo_acesso": self.ultimo_acesso.isoformat() if self.ultimo_acesso else None,
            "id_empresa": self.id_empresa,
            "avatar_url": self._avatar_url(),
        }
        if incluir_sensiveis:
            from src.core.security import aes_decrypt

            d["cpf"] = aes_decrypt(self.cpf)
            d["atributos_profissionais"] = papel.to_dict() if papel else None
        return d

    def to_dict_few(self):
        return {
            "uuid": self.uuid,
            "nome_completo": self.nome_completo,
            "email": self.email,
            "funcao_clinica": self.funcao_clinica,
            "status": self.status,
            "is_admin": self.is_admin,
            "avatar_url": self._avatar_url(),
        }

    def to_dict_session(self):
        return {
            "uuid": self.uuid,
            "funcao_clinica": self.funcao_clinica,
            "is_admin": self.is_admin,
            "is_super_admin": self.is_super_admin,
            "status": self.status,
        }
