"""
Dominio Paciente.

Paciente e PacientePessoal ja estavam quase completos no projeto original.
Alergia, DoencaCronica e MedicamentoEmUso nao existiam como classes
proprias (so eram citadas em relationship() sem definicao) -- criadas
aqui. Consentimento era stub; completado.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


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
