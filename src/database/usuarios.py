"""
Dominio de Usuarios (profissionais de saude, admins).

Usuario ja estava quase completo no projeto original; mantido. Configuracao
era um stub no original; completado com vinculo 1-para-1 com Usuario e um
JSON livre de preferencias/overrides de protocolo.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.database import db
from src.database.types import BigIntPK


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresa.id"), nullable=False)
    nome_completo = db.Column(db.String(255), nullable=False)
    cpf = db.Column(db.String(500), nullable=False)  # AES-256-GCM (valor exibível)
    cpf_hash = db.Column(db.String(64), unique=True, nullable=False)  # HMAC-SHA256 (índice de busca)
    email = db.Column(db.String(255), unique=True, nullable=False)
    telefone = db.Column(db.String(50))
    user_login = db.Column(db.String(100), unique=True)
    tipo_usuario = db.Column(db.Enum("medico", "enfermeiro", "admin"), nullable=False)
    status = db.Column(db.Enum("ativo", "inativo", "suspenso"),
                        nullable=False, default="ativo")
    atributos_profissionais_json = db.Column(db.JSON)
    hash_senha = db.Column(db.String(500), nullable=False)  # Argon2id
    mfa_habilitado = db.Column(db.Boolean, nullable=False, default=False)
    ultimo_acesso = db.Column(db.DateTime(timezone=True))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    empresa = db.relationship("Empresa", back_populates="usuarios")
    configuracao = db.relationship("Configuracao", back_populates="usuario",
                                    uselist=False, cascade="all, delete-orphan")

    def is_medico(self):
        return self.tipo_usuario == "medico"

    def is_enfermeiro(self):
        return self.tipo_usuario == "enfermeiro"

    def is_admin(self):
        return self.tipo_usuario == "admin"

    def to_dict(self, incluir_sensiveis=False):
        d = {
            "uuid": self.uuid,
            "nome_completo": self.nome_completo,
            "email": self.email,
            "telefone": self.telefone,
            "user_login": self.user_login,
            "tipo_usuario": self.tipo_usuario,
            "status": self.status,
            "ultimo_acesso": self.ultimo_acesso.isoformat() if self.ultimo_acesso else None,
        }
        if incluir_sensiveis:
            from src.core.security import aes_decrypt
            d["cpf"] = aes_decrypt(self.cpf)
            d["atributos_profissionais"] = self.atributos_profissionais_json
        return d

    def __repr__(self):
        return f"<Usuario {self.uuid} [{self.tipo_usuario}]>"


class Configuracao(db.Model):
    __tablename__ = "configuracao"

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_usuario = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"),
                            unique=True, nullable=False)
    configuracoes_json = db.Column(db.JSON)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    usuario = db.relationship("Usuario", back_populates="configuracao")

    def to_dict(self):
        return {"uuid": self.uuid, "configuracoes": self.configuracoes_json}

    def __repr__(self):
        return f"<Configuracao {self.uuid}>"
