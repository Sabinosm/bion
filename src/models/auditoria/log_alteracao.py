from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class LogAlteracao(db.Model):
    __tablename__ = "log_alteracao"

    __table_args__ = (
        db.Index("ix_log_alteracao_empresa_data", "id_empresa", "alterado_em"),
        db.Index("ix_log_alteracao_usuario_data", "alterado_por", "alterado_em"),
        db.Index("ix_log_alteracao_registro_data", "uuid_registro", "alterado_em"),
        db.Index("ix_log_alteracao_empresa_acao", "id_empresa", "acao"),
    )

    id = db.Column("id_alteracao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_alteracao",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"), nullable=False)
    acao = db.Column(db.String(100))
    tabela_origem = db.Column(db.String(100), nullable=False)
    id_registro = db.Column(db.BigInteger, nullable=False)
    uuid_registro = db.Column(db.String(36), nullable=False)
    operacao = db.Column(db.Enum("INSERT", "UPDATE", "DELETE"), nullable=False)
    campo_alterado = db.Column(db.String(100))
    valor_anterior = db.Column(db.Text)
    valor_novo = db.Column(db.Text)
    alterado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    ip_origem = db.Column(db.String(255))
    justificativa = db.Column(db.Text)
    alterado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    usuario = db.relationship("Usuario")
    empresa = db.relationship("Empresa")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "acao": self.acao,
            "tabela_origem": self.tabela_origem,
            "operacao": self.operacao,
            "campo_alterado": self.campo_alterado,
            "valor_anterior": self.valor_anterior,
            "valor_novo": self.valor_novo,
            "justificativa": self.justificativa,
            "alterado_em": self.alterado_em.isoformat() if self.alterado_em else None,
        }

    def to_dict_resumido(self):
        frase_acao = self.acao or (
            f"{self.operacao} em {self.tabela_origem}"
            + (f".{self.campo_alterado}" if self.campo_alterado else "")
        )
        return {
            "uuid": self.uuid,
            "frase_acao": frase_acao,
            "data_hora": self.alterado_em.isoformat() if self.alterado_em else None,
        }

    def __repr__(self):
        return f"<LogAlteracao {self.uuid} [{self.acao or self.operacao} em {self.tabela_origem}]>"
