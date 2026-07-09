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

    id = db.Column("id_usuario", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_usuario", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresa.id_empresa"), nullable=False)
    google_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    nome_completo = db.Column(db.String(255), nullable=False)
    cpf = db.Column(db.String(500), nullable=False)  # AES-256-GCM (valor exibível)
    email = db.Column(db.String(255), unique=True, nullable=False)
    telefone = db.Column(db.String(50))
    user_login = db.Column(db.String(100), unique=True)
    tipo_usuario = db.Column(db.Enum("medico", "enfermeiro", "admin"), nullable=False)
    status = db.Column(db.Enum("ativo", "inativo", "suspenso"),
                        nullable=False, default="ativo")
    atributos_profissionais_json = db.Column(db.JSON)
    hash_senha = db.Column(db.String(255), nullable=True)  # Argon2id
    onboarding_pendente = db.Column(db.Boolean, default=True, nullable=False)
    ultimo_acesso = db.Column(db.DateTime(timezone=True))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)
    cpf_hash = db.Column(db.String(255), nullable=False)

    empresa = db.relationship("Empresa", back_populates="usuarios")
    configuracao = db.relationship("Configuracao", back_populates="usuario",
                                    uselist=False, cascade="all, delete-orphan")

    def is_medico(self):
        return self.tipo_usuario == "medico"

    def is_enfermeiro(self):
        return self.tipo_usuario == "enfermeiro"

    def is_admin(self):
        return self.tipo_usuario == "admin"

    #TODO verificar se todos os dados aqui são utilizaveis no momento em que são entregues 
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
            "id_empresa" : self.id_empresa
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

    id = db.Column("id_configuracao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_configuracao", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_usuario = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"),
                            unique=True, nullable=False)
    configuracoes_json = db.Column(db.JSON)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    usuario = db.relationship("Usuario", back_populates="configuracao")
    protocolos = db.relationship("ConfiguracaoProtocolo", back_populates="configuracao",
                                  cascade="all, delete-orphan")
    
    # Quebrar configuracoes_json
    def to_dict(self):
        # "design": {
        #     "tema": "claro",
        #     "tamanho_fonte": "medio",
        # },
        # "preferencias": {
        #     "linguagem": ["pt-BR"]
        # }
        
        return {
            "uuid": self.uuid,
            "design": self.configuracoes_json["design"],
            "preferencias": self.configuracoes_json["preferencias"],
            "protocolos": {
                #
                (p.protocolo.sigla if p.protocolo else p.id_protocolo): {
                    "nome": p.protocolo.nome_protocolo if p.protocolo else None,
                    "tipo": p.protocolo.tipo_protocolo if p.protocolo else None,
                    "id": p.id_protocolo,
                }
                for p in self.protocolos
            }
        }

    def __repr__(self):
        return f"<Configuracao {self.uuid}>"
    

class ConfiguracaoProtocolo(db.Model):
    __tablename__ = "configuracao_protocolo"

    id = db.Column("id_configuracao_protocolo", BigIntPK, primary_key=True, autoincrement=True)
    id_configuracao = db.Column(db.BigInteger, db.ForeignKey("configuracao.id_configuracao"),
                                 nullable=False)
    id_protocolo = db.Column(db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"),
                              nullable=True)

    configuracao = db.relationship("Configuracao", back_populates="protocolos")
    protocolo = db.relationship("ProtocoloCatalogo") 

    def to_dict(self):
        return {
            "id": self.id,
            "id_protocolo": self.id_protocolo,
            "nome": self.protocolo.nome_protocolo if self.protocolo else None,
            "tipo": self.protocolo.tipo_protocolo if self.protocolo else None,
            "configuracoes": self.configuracao.configuracoes_json if self.configuracao else None,
        }

    def __repr__(self):
        return f"<ConfiguracaoProtocolo {self.id}>"

class CredencialWebAuthn(db.Model):
    """
    Guarda a CHAVE PÚBLICA de cada dispositivo/autenticador que o usuário
    cadastrou (ex: Face ID do celular, Windows Hello do notebook, Yubikey).
 
    Um mesmo usuário pode ter várias linhas aqui (um por dispositivo).
    A chave PRIVADA nunca existe no servidor — fica só no hardware do usuário.
    """
 
    __tablename__ = "credencial_webauthn"
 
    id_credencial = db.Column(db.BigInteger, primary_key=True)
    id_usuario = db.Column(
        db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False, index=True
    )
 
    # ID público da credencial, gerado pelo autenticador (base64url)
    credential_id = db.Column(db.String(512), unique=True, nullable=False, index=True)
 
    # Chave pública em bytes (formato COSE) — usada para VERIFICAR assinaturas
    public_key = db.Column(db.LargeBinary, nullable=False)
 
    # Contador anti-replay: incrementa a cada login: se vier um valor menor
    # ou igual ao salvo, pode ser um clone/replay da credencial -> bloquear
    sign_count = db.Column(db.BigInteger, nullable=False, default=0)
 
    # Nome amigável pro usuário identificar o dispositivo (opcional)
    apelido_dispositivo = db.Column(db.String(120), nullable=True)
 
    criado_em = db.Column(db.DateTime, server_default=db.func.now())