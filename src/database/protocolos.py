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

from src.database import db
from src.database.types import BigIntPK


class CatalogoFluxogramasMts(db.Model):
    __tablename__ = "catalogo_fluxogramas_mts"

    id = db.Column("id_fluxo_mts",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_fluxo_mts", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    codigo_fluxograma = db.Column(db.String(50), nullable=False)
    nome_fluxograma = db.Column(db.String(255), nullable=False)
    status = db.Column(db.Enum("ativo", "descontinuado"), nullable=False, default="ativo")
    estrutura_json = db.Column(db.JSON)

    protocolos_mts = db.relationship("ProtocoloMts", back_populates="fluxo_mts")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "codigo_fluxograma": self.codigo_fluxograma,
            "nome_fluxograma": self.nome_fluxograma,
            "status": self.status,
        }

    def __repr__(self):
        return f"<CatalogoFluxogramasMts {self.uuid} [{self.codigo_fluxograma}]>"


class CatalogoModulos(db.Model):
    __tablename__ = "catalogo_modulos"

    id = db.Column("id_modulo",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_modulo", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome_modulo = db.Column(db.String(255), nullable=False)
    tipo_modulo = db.Column(
        db.Enum("epidemiologico", "comorbidade", "faixa-etaria", "institucional"),
        nullable=False)
    status = db.Column(db.Enum("ativo", "inativo"), nullable=False, default="ativo")
    descricao = db.Column(db.Text)
    campos_adicionados_json = db.Column(db.JSON)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    protocolos_personalizados = db.relationship("ProtocoloPersonalizado", back_populates="modulo")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome_modulo": self.nome_modulo,
            "tipo_modulo": self.tipo_modulo,
            "status": self.status,
            "descricao": self.descricao,
        }

    def __repr__(self):
        return f"<CatalogoModulos {self.uuid} [{self.nome_modulo}]>"


class OutputBion(db.Model):
    __tablename__ = "output_bion"

    id = db.Column("id_output", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_output", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_input = db.Column(db.BigInteger, db.ForeignKey("input_protocolo.id_input"))
    output_ia_json = db.Column(db.JSON)
    versao_modelo_ia = db.Column(db.String(50))
    indice_completude = db.Column(db.Numeric(5, 2))
    indice_confianca = db.Column(db.Numeric(5, 2))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    input_protocolo = db.relationship("InputProtocolo", back_populates="outputs")
    resultados_prescricao = db.relationship("ResultadoPrescricao", back_populates="output_bion")
    prescricoes_exame = db.relationship("PrescricaoExame", back_populates="output_origem")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "output_ia": self.output_ia_json,
            "versao_modelo_ia": self.versao_modelo_ia,
            "indice_completude": float(self.indice_completude) if self.indice_completude is not None else None,
            "indice_confianca": float(self.indice_confianca) if self.indice_confianca is not None else None,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }

    def __repr__(self):
        return f"<OutputBion {self.uuid}>"


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


class ProtocoloMts(db.Model):
    __tablename__ = "protocolo_mts"

    id = db.Column("id_protocolo_mts", BigIntPK, primary_key=True, autoincrement=True)
    id_fluxo_mts = db.Column(db.BigInteger, db.ForeignKey("catalogo_fluxogramas_mts.id_fluxo_mts"))
    id_protocolo_catalogo = db.Column(db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"))

    fluxo_mts = db.relationship("CatalogoFluxogramasMts", back_populates="protocolos_mts")
    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="protocolos_mts")

    def __repr__(self):
        return f"<ProtocoloMts {self.id}>"


class ProtocoloPersonalizado(db.Model):
    __tablename__ = "protocolo_personalizado"

    id = db.Column("id_protocolo_personalizado", BigIntPK, primary_key=True, autoincrement=True)
    id_modulo = db.Column(db.BigInteger, db.ForeignKey("catalogo_modulos.id_modulo"))
    id_protocolo_catalogo = db.Column(db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"))
    codigo_protocolo = db.Column(db.String(100))

    modulo = db.relationship("CatalogoModulos", back_populates="protocolos_personalizados")
    protocolo_catalogo = db.relationship("ProtocoloCatalogo",
                                          back_populates="protocolos_personalizados")

    def __repr__(self):
        return f"<ProtocoloPersonalizado {self.id}>"
