"""
Dominio Paciente.

ALTERADO: tipo_reacao, gravidade e descricao_reacao SAÍRAM como colunas
diretas -- viram ReacaoAlergia (lista, permite múltiplas reações por
alergia). Propriedades de compatibilidade abaixo leem a reação MAIS
RECENTE, para que to_dict() e código existente continuem funcionando
sem alteração perceptível (mesmo padrão usado nos domínios anteriores).
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Alergia(db.Model):
    __tablename__ = "alergia"
    __table_args__ = (
        db.Index("idx_alergia_deletado", "deletado"),
        db.Index("idx_alergia_paciente_deletado", "id_paciente", "deletado"),
    )

    id = db.Column("id_alergia", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_alergia", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    substancia = db.Column(db.String(255), nullable=False)
    codigo_substancia = db.Column(db.String(100))
    sistema_codigo_substancia = db.Column(db.String(50), default="http://snomed.info/sct")
    # tipo_reacao, gravidade, descricao_reacao REMOVIDOS como colunas -- ver ReacaoAlergia
    flag_confirmado = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)
    # NOVO: soft delete -- mesmo padrão de DoencaCronica. `deletado` é
    # campo independente de flag_confirmado (que é sobre confiabilidade
    # clínica do dado, não sobre existência do registro). Um dos
    # motivos de delete é 'solicitacao-paciente', onde a alergia
    # continua clinicamente válida -- por isso não reaproveitamos
    # nenhum campo clínico existente pra marcar "removido".
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

    paciente = db.relationship("Paciente", back_populates="alergias")
    reacoes = db.relationship("ReacaoAlergia", back_populates="alergia",
                               cascade="all, delete-orphan")

    @property
    def tipo_reacao(self):
        """Compatibilidade: retorna a manifestação da reação mais recente."""
        return self.reacoes[-1].manifestacao if self.reacoes else None

    @property
    def gravidade(self):
        """Compatibilidade: retorna a gravidade da reação mais recente."""
        return self.reacoes[-1].gravidade if self.reacoes else None

    @property
    def descricao_reacao(self):
        """Compatibilidade: retorna a descrição da reação mais recente."""
        return self.reacoes[-1].descricao if self.reacoes else None

    def registrar_reacao(self, manifestacao: str, gravidade: str, descricao: str = None,
                          data_ocorrencia=None):
        """Adiciona uma nova reação ao histórico desta alergia.

        Substitui a antiga forma de sobrescrever tipo_reacao/gravidade
        direto -- agora cada ocorrência fica registrada, sem perder o
        histórico anterior.
        """
        from src.models.pacientes.reacao_alergia import ReacaoAlergia
        self.reacoes.append(ReacaoAlergia(
            manifestacao=manifestacao,
            gravidade=gravidade,
            descricao=descricao,
            data_ocorrencia=data_ocorrencia,
        ))

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "substancia": self.substancia,
            "tipo_reacao": self.tipo_reacao,
            "gravidade": self.gravidade,
            "descricao_reacao": self.descricao_reacao,
            "flag_confirmado": self.flag_confirmado,
            "reacoes": [r.to_dict() for r in self.reacoes],  # histórico completo, se o front quiser
        }

    def __repr__(self):
        return f"<Alergia {self.uuid} [{self.substancia}]>"