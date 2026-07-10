from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK

class LogAcesso(db.Model):
    __tablename__ = "log_acesso"

    id = db.Column("id_log",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_log",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_usuario = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    recurso_acessado = db.Column(db.String(255), nullable=False)
    operacao = db.Column(
        db.Enum("leitura", "escrita", "exclusao-logica", "exportacao"), nullable=False)
    data_hora = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    ip_origem = db.Column(db.String(255), nullable=False)
    resultado = db.Column(
        db.Enum("sucesso", "falha-autenticacao", "acesso-negado", "timeout"), nullable=False)
    uuid_paciente = db.Column(db.String(36))  # referencia leve, sem FK, p/ nao acoplar dominio
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    usuario = db.relationship("Usuario")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "recurso_acessado": self.recurso_acessado,
            "operacao": self.operacao,
            "data_hora": self.data_hora.isoformat() if self.data_hora else None,
            "resultado": self.resultado,
        }

    def __repr__(self):
        return f"<LogAcesso {self.uuid} [{self.operacao}/{self.resultado}]>"