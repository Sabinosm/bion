"""
Dominio Clinico (nucleo do ciclo de vida do atendimento/visita).

Consulta, Atendimento e SinalVital ja estavam completos no projeto
original. ColetaClinica, ResultadoPrescricao, InputProtocolo,
InputProtocoloExecucao, Prescricao e PrescricaoExame eram stubs ou nem
existiam como classe -- completados aqui com os campos do schema.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class ResultadoPrescricao(db.Model):
    __tablename__ = "resultado_prescricao"

    id = db.Column("id_resultado", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_resultado", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_atendimento = db.Column(db.BigInteger, db.ForeignKey("atendimento.id_atendimento"), nullable=False)
    id_output = db.Column(db.BigInteger, db.ForeignKey("output_bion.id_output"))
    codigo_cid10_principal = db.Column(db.String(10), nullable=False)
    descricao_cid10_principal = db.Column(db.String(255), nullable=False)
    certeza_diagnostica = db.Column(
        db.Enum("suspeito", "provavel", "confirmado", "descartado"), nullable=False)
    tipo_prescricao = db.Column(
        db.Enum("farmacologica", "nao-farmacologica", "encaminhamento", "internacao", "alta"))
    consistente_com_classificacao = db.Column(db.Boolean)
    formulado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    data_hora_formulacao = db.Column(db.DateTime(timezone=True), nullable=False,
                                      default=lambda: datetime.now(timezone.utc))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)
    # rascunho: proposta (IA ou médico) ainda editável; confirmado: o médico responde por ela;
    # descartado: o médico desistiu do rascunho (descarte LÓGICO: a linha e os itens ficam).
    status = db.Column(db.Enum("rascunho", "confirmado", "descartado"), nullable=False, default="rascunho")
    confirmado_em = db.Column(db.DateTime(timezone=True))
    # Quem responde pelo conteúdo hoje: 'bion_ia' enquanto o médico não mexeu em NADA (diagnóstico,
    # itens, adição ou remoção); qualquer alteração dele passa para 'medico'. id_output continua
    # apontando para a avaliação que originou o rascunho (rastro do que a IA sugeriu).
    origem_sugestao = db.Column(db.Enum("medico", "bion_ia", "protocolo"), nullable=False, default="medico")
    descartado_em = db.Column(db.DateTime(timezone=True))
    descartado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    motivo_descarte = db.Column(db.Text)

    atendimento = db.relationship("Atendimento", back_populates="resultados_prescricao")
    output_bion = db.relationship("OutputBion", back_populates="resultados_prescricao")
    usuario = db.relationship("Usuario", foreign_keys=[formulado_por])
    usuario_descarte = db.relationship("Usuario", foreign_keys=[descartado_por])
    prescricoes = db.relationship("Prescricao", back_populates="resultado_prescricao",
                                   cascade="all, delete-orphan")
    prescricoes_exame = db.relationship("PrescricaoExame", back_populates="resultado_prescricao",
                                         cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "codigo_cid10_principal": self.codigo_cid10_principal,
            "descricao_cid10_principal": self.descricao_cid10_principal,
            "certeza_diagnostica": self.certeza_diagnostica,
            "tipo_prescricao": self.tipo_prescricao,
            "status": self.status,
            "origem_sugestao": self.origem_sugestao,
            "atendimento_uuid": self.atendimento.uuid if self.atendimento else None,
            "confirmado_em": self.confirmado_em.isoformat() if self.confirmado_em else None,
            "descartado_em": self.descartado_em.isoformat() if self.descartado_em else None,
            "motivo_descarte": self.motivo_descarte,
            "data_hora_formulacao": self.data_hora_formulacao.isoformat()
            if self.data_hora_formulacao else None,
            "medicamentos": [p.to_dict() for p in self.prescricoes],
            "exames": [e.to_dict() for e in self.prescricoes_exame],
        }

    def __repr__(self):
        return f"<ResultadoPrescricao {self.uuid} [{self.codigo_cid10_principal}]>"