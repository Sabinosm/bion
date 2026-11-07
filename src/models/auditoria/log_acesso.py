from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class LogAcesso(db.Model):
    __tablename__ = "log_acesso"

    __table_args__ = (
        db.Index("ix_log_acesso_empresa_data", "id_empresa", "data_hora"),
        db.Index("ix_log_acesso_usuario_data", "id_usuario", "data_hora"),
    )

    id = db.Column("id_log", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_log", db.String(36), unique=True, nullable=False, default=lambda: str(_uuid.uuid4())
    )
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"), nullable=False)
    id_usuario = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    recurso_acessado = db.Column(db.String(255), nullable=False)
    operacao = db.Column(
        db.Enum("leitura", "escrita", "exclusao-logica", "exportacao"), nullable=False
    )
    data_hora = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    ip_origem = db.Column(db.String(255), nullable=False)
    resultado = db.Column(
        db.Enum("sucesso", "falha-autenticacao", "acesso-negado", "timeout"), nullable=False
    )
    motivo_negacao = db.Column(db.String(255))
    uuid_paciente = db.Column(db.String(36))
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    usuario = db.relationship("Usuario")
    empresa = db.relationship("Empresa")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "recurso_acessado": self.recurso_acessado,
            "operacao": self.operacao,
            "data_hora": self.data_hora.isoformat() if self.data_hora else None,
            "resultado": self.resultado,
            "motivo_negacao": self.motivo_negacao,
        }

    def to_dict_resumido(self):
        return {
            "uuid": self.uuid,
            "frase_acao": f"{self.operacao} em {self.recurso_acessado}",
            "data_hora": self.data_hora.isoformat() if self.data_hora else None,
        }

    def __repr__(self):
        return f"<LogAcesso {self.uuid} [{self.operacao}/{self.resultado}]>"
