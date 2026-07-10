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
