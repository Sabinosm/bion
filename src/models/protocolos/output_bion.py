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
        # Validação dos índices de qualidade (0 a 100)
        db.CheckConstraint(
            'indice_completude IS NULL OR (indice_completude >= 0 AND indice_completude <= 100)',
            name='ck_output_bion_indice_completude'
        ),
        db.CheckConstraint(
            'indice_confianca IS NULL OR (indice_confianca >= 0 AND indice_confianca <= 100)',
            name='ck_output_bion_indice_confianca'
        ),
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
    # Auditoria das requisições/chamadas enviadas à IA
    requisicoes_ia_json = db.Column(db.JSON)
    # Versão do formato dos blocos do InputModel (para ler snapshots antigos).
    versao_input_model = db.Column(db.SmallInteger)
    # NULL = enviado e ainda sem resposta (ou a chamada falhou).
    output_ia_json = db.Column(db.JSON)
    versao_modelo_ia = db.Column(db.String(50))
    indice_completude = db.Column(db.Numeric(5, 2))
    indice_confianca = db.Column(db.Numeric(5, 2))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    atendimento = db.relationship("Atendimento", back_populates="outputs_bion")
    resultados_prescricao = db.relationship("ResultadoPrescricao", back_populates="output_bion")
    prescricoes_exame = db.relationship("PrescricaoExame", back_populates="output_origem")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "versao_input_model": self.versao_input_model,
            "input_ia": self.input_ia_json,
            "requisicoes_ia": self.requisicoes_ia_json,
            "output_ia": self.output_ia_json,
            "versao_modelo_ia": self.versao_modelo_ia,
            "indice_completude": float(self.indice_completude) if self.indice_completude is not None else None,
            "indice_confianca": float(self.indice_confianca) if self.indice_confianca is not None else None,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }

    def __repr__(self):
        return f"<OutputBion {self.uuid}>"