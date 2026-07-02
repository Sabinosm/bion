"""
Dominio Paciente.

Paciente e PacientePessoal ja estavam quase completos no projeto original.
Alergia, DoencaCronica e MedicamentoEmUso nao existiam como classes
proprias (so eram citadas em relationship() sem definicao) -- criadas
aqui. Consentimento era stub; completado.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.database import db
from src.database.types import BigIntPK


class Paciente(db.Model):
    __tablename__ = "paciente"

    id = db.Column("id_paciente", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_paciente", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    identificacao_anonima = db.Column(db.String(64))
    sexo_biologico = db.Column(db.Enum("M", "F", "I"), nullable=False)
    tipo_sanguineo = db.Column(db.String(10))
    data_nascimento = db.Column(db.Date)
    id_regiao_geografica = db.Column(db.BigInteger, db.ForeignKey("regiao_geografica.id_regiao_geografica"))
    data_primeiro_atendimento = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum("ativo", "inativo", "obito"),
                        nullable=False, default="ativo")
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)
    cadastrado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))

    regiao_geografica = db.relationship("RegiaoGeografica", back_populates="pacientes")
    pessoal = db.relationship("PacientePessoal", back_populates="paciente",
                               uselist=False, cascade="all, delete-orphan")
    alergias = db.relationship("Alergia", back_populates="paciente",
                                cascade="all, delete-orphan")
    doencas = db.relationship("DoencaCronica", back_populates="paciente",
                               cascade="all, delete-orphan")
    medicamentos_em_uso = db.relationship("MedicamentoEmUso", back_populates="paciente",
                                           cascade="all, delete-orphan")
    consentimentos = db.relationship("Consentimento", back_populates="paciente",
                                      cascade="all, delete-orphan")
    consultas = db.relationship("Consulta", back_populates="paciente")

    def esta_anonimizado(self):
        return self.pessoal is None

    def anonimizar(self, cpf_plaintext: str):
        from src.core.security import hmac_sha256
        self.identificacao_anonima = hmac_sha256(cpf_plaintext)

    def to_dict(self, incluir_pessoal=False):
        d = {
            "uuid": self.uuid,
            "sexo_biologico": self.sexo_biologico,
            "tipo_sanguineo": self.tipo_sanguineo,
            "data_nascimento": self.data_nascimento.isoformat() if self.data_nascimento else None,
            "status": self.status,
            "data_primeiro_atendimento": self.data_primeiro_atendimento.isoformat()
            if self.data_primeiro_atendimento else None,
        }
        if incluir_pessoal and self.pessoal:
            d["pessoal"] = self.pessoal.to_dict()
        return d

    def __repr__(self):
        return f"<Paciente {self.uuid}>"


class PacientePessoal(db.Model):
    __tablename__ = "paciente_pessoal"

    id = db.Column("id_paciente_p", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_paciente_p", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"),
                             unique=True, nullable=False)
    nome_completo = db.Column(db.String(500), nullable=False)   # AES-256
    cpf = db.Column(db.String(500))                             # AES-256 (valor exibível)
    cpf_hash = db.Column(db.String(64), unique=True)             # HMAC-SHA256 (índice de busca)
    rg = db.Column(db.String(100))
    telefone = db.Column(db.String(200))                        # AES-256
    email = db.Column(db.String(500))                           # AES-256
    logradouro = db.Column(db.String(500))                      # AES-256
    numero_residencia = db.Column(db.String(50))
    cep = db.Column(db.String(200))                             # AES-256
    contato_emergencia_nome = db.Column(db.String(255))
    contato_emergencia_telefone = db.Column(db.String(200))     # AES-256

    paciente = db.relationship("Paciente", back_populates="pessoal")

    def to_dict(self):
        return {
            "nome_completo": self.nome_completo,
            "rg": self.rg,
            "numero_residencia": self.numero_residencia,
            "contato_emergencia_nome": self.contato_emergencia_nome,
        }

    def __repr__(self):
        return f"<PacientePessoal {self.uuid}>"


class Alergia(db.Model):
    __tablename__ = "alergia"

    id = db.Column("id_alergia", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_alergia", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    substancia = db.Column(db.String(255), nullable=False)
    codigo_substancia = db.Column(db.String(100))
    tipo_reacao = db.Column(
        db.Enum("cutanea", "respiratoria", "anafilaxia", "gastrointestinal",
                "cardiovascular", "sistemica"),
        nullable=False)
    gravidade = db.Column(db.Enum("leve", "moderada", "grave", "anafilaxia"),
                           nullable=False)
    descricao_reacao = db.Column(db.Text)
    flag_confirmado = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    paciente = db.relationship("Paciente", back_populates="alergias")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "substancia": self.substancia,
            "tipo_reacao": self.tipo_reacao,
            "gravidade": self.gravidade,
            "descricao_reacao": self.descricao_reacao,
            "flag_confirmado": self.flag_confirmado,
        }

    def __repr__(self):
        return f"<Alergia {self.uuid} [{self.substancia}]>"


class DoencaCronica(db.Model):
    __tablename__ = "doenca_cronica"

    id = db.Column("id_doenca_cronica", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_doenca_cronica", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    codigo_cid10 = db.Column(db.String(10), nullable=False)
    descricao_cid10 = db.Column(db.String(255), nullable=False)
    desde = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum("ativa", "em-remissao"), nullable=False)
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    paciente = db.relationship("Paciente", back_populates="doencas")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "codigo_cid10": self.codigo_cid10,
            "descricao_cid10": self.descricao_cid10,
            "desde": self.desde.isoformat() if self.desde else None,
            "status": self.status,
            "observacoes": self.observacoes,
        }

    def __repr__(self):
        return f"<DoencaCronica {self.uuid} [{self.codigo_cid10}]>"


class MedicamentoEmUso(db.Model):
    __tablename__ = "Medicamentos_em_uso"

    id = db.Column("id_medicamento_uso", BigIntPK, primary_key=True, autoincrement=True)
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    id_catalogo = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"), nullable=False)
    descricao = db.Column(db.Text)
    dose = db.Column(db.String(100))
    frequencia = db.Column(db.String(100))
    desde = db.Column(db.Date)
    flag_em_uso = db.Column(db.Boolean, default=True)

    paciente = db.relationship("Paciente", back_populates="medicamentos_em_uso")
    catalogo_medicamento = db.relationship("CatalogoMedicamentos",
                                            back_populates="medicamentos_em_uso")

    def to_dict(self):
        return {
            "id": self.id,
            "descricao": self.descricao,
            "dose": self.dose,
            "frequencia": self.frequencia,
            "desde": self.desde.isoformat() if self.desde else None,
            "flag_em_uso": self.flag_em_uso,
        }

    def __repr__(self):
        return f"<MedicamentoEmUso {self.id}>"


class Consentimento(db.Model):
    __tablename__ = "consentimento_lgpd"

    id = db.Column("id_consentimento", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_consentimento", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    coletado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    versao_termo = db.Column(db.String(50), nullable=False)
    data_consentimento = db.Column(db.DateTime(timezone=True), nullable=False)
    canal_coleta = db.Column(
        db.Enum("presencial-papel", "presencial-digital", "portal-online", "totem"),
        nullable=False)
    status = db.Column(db.Enum("ativo", "revogado", "expirado"),
                        nullable=False, default="ativo")
    escopo_consentimento_json = db.Column(db.JSON)
    data_revogacao = db.Column(db.DateTime(timezone=True))
    motivo_revogacao = db.Column(db.Text)
    hash_documento = db.Column(db.String(64))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    paciente = db.relationship("Paciente", back_populates="consentimentos")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "versao_termo": self.versao_termo,
            "data_consentimento": self.data_consentimento.isoformat()
            if self.data_consentimento else None,
            "canal_coleta": self.canal_coleta,
            "status": self.status,
            "data_revogacao": self.data_revogacao.isoformat() if self.data_revogacao else None,
        }

    def __repr__(self):
        return f"<Consentimento {self.uuid} [{self.status}]>"
