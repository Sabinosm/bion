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


class OutputBion(db.Model):
    __tablename__ = "output_bion"
    
    __table_args__ = (
        # vigente = último por atendimento (criado_em desc, id desc)
        db.Index('ix_output_bion_atendimento_criado', 'id_atendimento', 'criado_em'),
        db.Index('ix_output_bion_atendimento_status', 'id_atendimento', 'status'),
    )

    id = db.Column("id_output", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_output", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    # Uma linha por ENVIO à IA, criada ANTES da chamada. Só o último envio do
    # atendimento é válido; os anteriores ficam (insert-only).
    id_atendimento = db.Column(db.BigInteger, db.ForeignKey("atendimento.id_atendimento"),
                                nullable=False)
    # O que a IA recebeu, congelado (InputModel.to_dict(): binário, dados
    # clínicos, sinais vitais, input do protocolo, lacunas). Não se remonta.
    input_ia_json = db.Column(db.JSON)
    # Versão do formato dos blocos do InputModel (para ler snapshots antigos).
    versao_input_model = db.Column(db.SmallInteger)
    # Auditoria das requisicoes da IA a pool de metodos (lista de RequisicaoIA).
    requisicoes_ia_json = db.Column(db.JSON)
    # NULL = a IA nao deu resposta valida (ver status/erro_codigo).
    output_ia_json = db.Column(db.JSON)
    versao_modelo_ia = db.Column(db.String(50))
    indice_completude = db.Column(db.Numeric(5, 2))
    indice_confianca = db.Column(db.Numeric(5, 2))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)
    # Avaliacao assincrona: processando -> concluido | falhou (+ erro_codigo).
    status = db.Column(db.Enum("processando", "concluido", "falhou"), nullable=False,
                       default="processando")
    erro_codigo = db.Column(db.String(40))
    concluido_em = db.Column(db.DateTime(timezone=True))

    atendimento = db.relationship("Atendimento", back_populates="outputs_bion")
    resultados_prescricao = db.relationship("ResultadoPrescricao", back_populates="output_bion")
    prescricoes_exame = db.relationship("PrescricaoExame", back_populates="output_origem")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "versao_input_model": self.versao_input_model,
            "output_ia": self.output_ia_json,
            "versao_modelo_ia": self.versao_modelo_ia,
            "indice_completude": float(self.indice_completude) if self.indice_completude is not None else None,
            "indice_confianca": float(self.indice_confianca) if self.indice_confianca is not None else None,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "status": self.status,
            "erro_codigo": self.erro_codigo,
            "concluido_em": self.concluido_em.isoformat() if self.concluido_em else None,
        }

    def __repr__(self):
        return f"<OutputBion {self.uuid}>"