from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class PacienteDadosPessoais(db.Model):
    __tablename__ = "paciente_dados_pessoais"
    __table_args__ = (
        db.UniqueConstraint("id_empresa", "cpf_hash", name="uq_paciente_pessoal_empresa_cpf"),
    )

    id = db.Column("id_paciente_p", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_paciente_p",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    id_paciente = db.Column(
        db.BigInteger, db.ForeignKey("paciente.id_paciente"), unique=True, nullable=False
    )
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"), nullable=False)
    nome_completo = db.Column(db.String(500), nullable=False)
    cpf = db.Column(db.String(500))
    cpf_hash = db.Column(db.String(64), nullable=False)
    rg = db.Column(db.String(100))
    telefone = db.Column(db.String(200))
    email = db.Column(db.String(500))
    logradouro = db.Column(db.String(500))
    numero_residencia = db.Column(db.String(50))
    cep = db.Column(db.String(200))
    contato_emergencia_nome = db.Column(db.String(255))
    contato_emergencia_telefone = db.Column(db.String(200))

    paciente = db.relationship("Paciente", back_populates="pessoal")

    def cpf_plaintext(self):
        from src.core.security import aes_decrypt

        return aes_decrypt(self.cpf) if self.cpf else None

    def to_dict(self):
        return {
            "nome_completo": self.nome_completo,
            "rg": self.rg,
            "numero_residencia": self.numero_residencia,
            "contato_emergencia_nome": self.contato_emergencia_nome,
        }

    def __repr__(self):
        return f"<PacienteDadosPessoais {self.uuid}>"
