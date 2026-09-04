"""
Dominio Paciente.

ALTERADO (conforme 08_medicamentos_em_uso_migration.sql):
1. uuid ADICIONADO -- esta tabela era a única do domínio clínico sem
   uuid próprio, provável esquecimento no schema original.
2. status_uso ADICIONADO -- complementa flag_em_uso com granularidade
   ('ativo'/'interrompido'/'concluido'), mapeando melhor para
   MedicationStatement.status do FHIR do que um boolean simples.
   flag_em_uso MANTIDO, não removido -- status_uso é um complemento.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class MedicamentoEmUso(db.Model):
    __tablename__ = "medicamentos_em_uso"
    __table_args__ = (
        db.Index("idx_medicamento_em_uso_deletado", "deletado"),
        db.Index("idx_medicamento_em_uso_paciente_deletado", "id_paciente", "deletado"),
    )

    id = db.Column("id_medicamento_uso", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_medicamentos_uso", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    id_catalogo = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"), nullable=False)
    descricao = db.Column(db.Text)
    dose = db.Column(db.String(100))
    frequencia = db.Column(db.String(100))
    desde = db.Column(db.Date)
    flag_em_uso = db.Column(db.Boolean, default=True)
    status_uso = db.Column(db.Enum("ativo", "interrompido", "concluido"), nullable=True)
    # NOVO: soft delete -- mesmo padrão de Alergia/DoencaCronica.
    # `deletado` fica totalmente separado de status_uso/flag_em_uso de
    # propósito: um medicamento "interrompido" ou "concluido" é um
    # estado clínico real do tratamento, diferente de "removido do
    # sistema" (ex: cadastro duplicado, erro de digitação, ou
    # solicitação do paciente). Misturar os dois no mesmo campo faria
    # perder a distinção entre "parou de tomar" e "não devia existir
    # esse registro".
    deletado = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    deletado_em = db.Column(db.DateTime(timezone=True), nullable=True)
    motivo_delete = db.Column(
        db.Enum(
            "erro-digitacao",
            "registro-duplicado",
            "diagnostico-incorreto",
            "solicitacao-paciente",
            "outro",
        ),
        nullable=True,
    )
    observacoes_delete = db.Column(db.Text, nullable=True)

    paciente = db.relationship("Paciente", back_populates="medicamentos_em_uso")
    catalogo_medicamentos = db.relationship("CatalogoMedicamentos",
                                            back_populates="medicamentos_em_uso")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "descricao": self.descricao,
            "dose": self.dose,
            "frequencia": self.frequencia,
            "desde": self.desde.isoformat() if self.desde else None,
            "flag_em_uso": self.flag_em_uso,
            "status_uso": self.status_uso,
        }

    def __repr__(self):
        return f"<MedicamentoEmUso {self.uuid}>"