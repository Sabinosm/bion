"""
Dominio de Auditoria.

Logs imutaveis de acesso e de alteracao (trilha de auditoria), essenciais
para conformidade LGPD e rastreabilidade. Nao existiam como classes no
projeto original -- criados aqui com os campos do schema.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK



class LogAlteracao(db.Model):
    __tablename__ = "log_alteracao"

    id = db.Column("id_alteracao",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_alteracao",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    tabela_origem = db.Column(db.String(100), nullable=False)
    id_registro = db.Column(db.BigInteger, nullable=False)
    uuid_registro = db.Column(db.String(36), nullable=False)
    operacao = db.Column(db.Enum("INSERT", "UPDATE", "DELETE"), nullable=False)
    campo_alterado = db.Column(db.String(100))
    valor_anterior = db.Column(db.Text)
    valor_novo = db.Column(db.Text)
    alterado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    ip_origem = db.Column(db.String(45))
    justificativa = db.Column(db.Text)
    alterado_em = db.Column(db.DateTime(timezone=True),
                             default=lambda: datetime.now(timezone.utc), nullable=False)

    usuario = db.relationship("Usuario")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tabela_origem": self.tabela_origem,
            "operacao": self.operacao,
            "campo_alterado": self.campo_alterado,
            "alterado_em": self.alterado_em.isoformat() if self.alterado_em else None,
        }

    def __repr__(self):
        return f"<LogAlteracao {self.uuid} [{self.operacao} em {self.tabela_origem}]>"
