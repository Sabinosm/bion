"""
Dominio Clinico (nucleo do ciclo de vida do atendimento/visita).

Atualizado com as colunas adicionadas via ALTER TABLE
input_protocolo_execucao (secao 4 do SQL de 2026-09-24):
  executor, timestamp_execucao, status, id_versao_utilizada,
  dados_ausentes_json, resultado_calculado_json.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class InputProtocoloExecucao(db.Model):
    __tablename__ = "input_protocolo_execucao"

    id = db.Column("id_input_execucao", BigIntPK, primary_key=True, autoincrement=True)
    id_input = db.Column(db.BigInteger, db.ForeignKey("input_protocolo.id_input"))
    id_protocolo_catalogo = db.Column(db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"))

    executor = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=True)
    timestamp_execucao = db.Column(db.DateTime(timezone=True),
                                    default=lambda: datetime.now(timezone.utc), nullable=False)
    status = db.Column(db.Enum("concluida", "incompleta", "cancelada"),
                        nullable=False, default="concluida")
    id_versao_utilizada = db.Column(db.BigInteger, db.ForeignKey("protocolo_versao.id_versao"),
                                     nullable=True)
    dados_ausentes_json = db.Column(db.JSON, nullable=True)
    resultado_calculado_json = db.Column(db.JSON, nullable=True)

    input_protocolo = db.relationship("InputProtocolo", back_populates="execucoes")
    protocolo_catalogo = db.relationship("ProtocoloCatalogo")
    versao_utilizada = db.relationship("ProtocoloVersao", back_populates="execucoes")
    usuario_executor = db.relationship("Usuarios", foreign_keys=[executor])

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "timestamp_execucao": self.timestamp_execucao.isoformat() if self.timestamp_execucao else None,
            "dados_ausentes": self.dados_ausentes_json,
            "resultado_calculado": self.resultado_calculado_json,
        }

    def __repr__(self):
        return f"<InputProtocoloExecucao {self.id}>"