"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

ProtocoloCatalogo era um stub (so id/uuid/criado_em), mas o
ProtocoloFactory (app/protocolo/factory.py) ja acessava `catalogo.sigla`
para escolher o motor certo (MTS/NEWS2/PP) -- isso quebraria em runtime
assim que a factory fosse chamada. Completado aqui com sigla e os demais
campos do schema.

OutputBion tambem era stub, mas ia/controller.py ja acessava
`output.output_ia_json` -- tambem completado.
"""

from datetime import datetime, timezone
import uuid as _uuid
import decimal

from src.models import db
from src.models.types import BigIntPK


class ProtocoloCatalogo(db.Model):
    __tablename__ = "protocolo_catalogo"

    id = db.Column("id_protocolo_catalogo", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_protocolo_catalogo", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome_protocolo = db.Column(db.String(255), nullable=False)
    sigla = db.Column(db.String(50), unique=True, nullable=False)  # usado por ProtocoloFactory
    tipo_resultado = db.Column(
        db.Enum("score-numerico", "categoria-cor", "nivel-risco", "binario"),
        nullable=False)
    tipo_protocolo = db.Column(db.String(100))
    escopo_populacao = db.Column(
        db.Enum("adulto", "pediatrico", "obstetrico", "neonatal", "universal"),
        nullable=False, default="universal")
    escopo_uso = db.Column(db.Enum("triagem", "consulta", "ambos"), default="ambos")
    versao_vigente = db.Column(db.String(50), nullable=False)
    data_vigencia = db.Column(db.Date, nullable=False)
    data_vigencia_fim = db.Column(db.Date)
    status = db.Column(db.Enum("ativo", "descontinuado", "em-revisao"),
                        nullable=False, default="ativo")
    referencia_bibliografica = db.Column(db.Text)
    orgao_emissor = db.Column(db.String(255))
    flag_personalizado = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    protocolos_mts = db.relationship("ProtocoloMts", back_populates="protocolo_catalogo")
    protocolos_personalizados = db.relationship("ProtocoloPersonalizado",
                                                 back_populates="protocolo_catalogo")
    execucoes = db.relationship("InputProtocoloExecucao", back_populates="protocolo_catalogo")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome_protocolo": self.nome_protocolo,
            "sigla": self.sigla,
            "tipo_resultado": self.tipo_resultado,
            "escopo_populacao": self.escopo_populacao,
            "escopo_uso": self.escopo_uso,
            "versao_vigente": self.versao_vigente,
            "status": self.status,
        }

    def __repr__(self):
        return f"<ProtocoloCatalogo {self.uuid} [{self.sigla}]>"
