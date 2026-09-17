"""
Modelo de Usuario (profissionais de saude e admins da empresa).

O papel clinico (medico/enfermeiro) fica em PapelProfissional, nao aqui.
funcao_clinica() expoe esse papel; is_admin/is_super_admin controlam
privilegios administrativos. As duas dimensoes sao independentes: um
usuario pode ser admin e tambem ter um papel clinico ativo ao mesmo tempo.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column("id_usuario", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_usuario", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"), nullable=False)
    google_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    nome_completo = db.Column(db.String(255), nullable=False)
    cpf = db.Column(db.String(500), nullable=False)  # AES-256-GCM (valor exibivel)
    email = db.Column(db.String(255), unique=True, nullable=False)
    telefone = db.Column(db.String(50))
    user_login = db.Column(db.String(100), unique=True)

    is_admin = db.Column("is_admin", db.Boolean, nullable=False, default=False)

    # Admin fundador da empresa (criado em Empresa.cadastrar_com_admin).
    # Unico com poder de criar/alterar outros admins; nunca pode ser
    # rebaixado ou desativado por ninguem, nem por si mesmo.
    is_super_admin = db.Column("is_super_admin", db.Boolean, nullable=False, default=False)

    status = db.Column(db.Enum("ativo", "inativo", "pendente"),
                        nullable=False, default="pendente")
    hash_senha = db.Column(db.String(255), nullable=True)  # Argon2id

    # Incrementado a cada troca de hash_senha. Usado pelo decorator
    # requer_senha_atualizada (src/core/session.py) para invalidar
    # sessoes desatualizadas em leituras sensiveis (dados de paciente).
    senha_versao = db.Column("senha_versao", db.Integer, nullable=False, default=1)

    onboarding_pendente = db.Column(db.Boolean, default=True, nullable=False)
    ultimo_acesso = db.Column(db.DateTime(timezone=True))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)
    cpf_hash = db.Column(db.String(255), nullable=False)

    empresa = db.relationship("Empresa", back_populates="usuarios")
    configuracao = db.relationship("Configuracao", back_populates="usuario",
                                    uselist=False, cascade="all, delete-orphan")
    papeis = db.relationship("PapelProfissional", back_populates="usuario",
                              cascade="all, delete-orphan")

    def papel_ativo(self):
        """Retorna a instancia de PapelProfissional ativa, ou None (ex: admin puro).

        Um usuario tem no maximo um papel profissional ativo por vez.
        """
        return next((p for p in self.papeis if p.ativo), None)

    @property
    def funcao_clinica(self):
        """Papel clinico do usuario ("medico", "enfermeiro" ou None).

        Nao reflete status administrativo: is_admin e a unica fonte de
        verdade para isso. Nao e coluna do banco, entao nao pode ser usada
        em filtros de query (ver repository.find_by_tipo_papel).
        """
        papel = self.papel_ativo()
        return papel.tipo_papel if papel else None

    def is_medico(self):
        papel = self.papel_ativo()
        return bool(papel and papel.tipo_papel == "medico")

    def is_enfermeiro(self):
        papel = self.papel_ativo()
        return bool(papel and papel.tipo_papel == "enfermeiro")

    def to_dict(self, incluir_sensiveis=False):
        """Representacao completa do usuario para respostas de API."""
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
        }
        if incluir_sensiveis:
            from src.core.security import aes_decrypt
            d["cpf"] = aes_decrypt(self.cpf)
            d["atributos_profissionais"] = papel.to_dict() if papel else None
        return d

    def to_dict_few(self):
        """Representacao resumida do usuario, usada em listagens."""
        return {
            "uuid": self.uuid,
            "nome_completo": self.nome_completo,
            "email": self.email,
            "funcao_clinica": self.funcao_clinica,
            "status": self.status,
            "is_admin": self.is_admin,
        }