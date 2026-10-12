"""
Dominio Paciente.

ALTERADO: tipo_reacao, gravidade e descricao_reacao SAÍRAM como colunas
diretas -- viram ReacaoAlergia (lista, permite múltiplas reações por
alergia). Propriedades de compatibilidade abaixo leem a reação ATIVA mais
recente, para que to_dict() e código existente continuem funcionando
sem alteração perceptível.

ALTERADO (Bloco 2): histórico clínico completo -- quem registrou e em
qual Atendimento (criado_por, id_atendimento_origem), e quem removeu e em
qual Atendimento (deletado_por, id_atendimento_delecao). Nullable porque
registros anteriores ao Bloco 2 não têm essa informação.

ALTERADO (Bloco 2): `reacoes` não tem mais delete-orphan nem cascade de
delete (nada se apaga): passive_deletes="all" + FK ON DELETE RESTRICT.
Ordenadas por criado_em e id, para que "a mais recente" seja a última.
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

    # NOVO (Bloco 2): autoria e atendimento de origem do registro.
    criado_por = db.Column(db.BigInteger,
                            db.ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    id_atendimento_origem = db.Column(db.BigInteger,
                                       db.ForeignKey("atendimento.id_atendimento", ondelete="RESTRICT"))

    # Soft delete -- `deletado` é independente de flag_confirmado (que é
    # sobre confiabilidade clínica do dado, não sobre existência do registro).
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
    # NOVO (Bloco 2): quem removeu e em qual Atendimento.
    deletado_por = db.Column(db.BigInteger,
                              db.ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"), nullable=True)
    id_atendimento_delecao = db.Column(db.BigInteger,
                                        db.ForeignKey("atendimento.id_atendimento", ondelete="RESTRICT"),
                                        nullable=True)

    paciente = db.relationship("Paciente", back_populates="alergias")
    usuario_criacao = db.relationship("Usuario", foreign_keys=[criado_por])
    atendimento_origem = db.relationship("Atendimento", foreign_keys=[id_atendimento_origem])
    reacoes = db.relationship(
        "ReacaoAlergia", back_populates="alergia",
        cascade="save-update, merge", passive_deletes="all",
        order_by="ReacaoAlergia.criado_em, ReacaoAlergia.id",
    )

    @property
    def reacoes_ativas(self):
        """Reações não removidas, da mais antiga para a mais recente."""
        return [r for r in self.reacoes if not r.deletado]

    @property
    def tipo_reacao(self):
        """Compatibilidade: manifestação da reação ativa mais recente."""
        ativas = self.reacoes_ativas
        return ativas[-1].manifestacao if ativas else None

    @property
    def gravidade(self):
        """Compatibilidade: gravidade da reação ativa mais recente."""
        ativas = self.reacoes_ativas
        return ativas[-1].gravidade if ativas else None

    @property
    def descricao_reacao(self):
        """Compatibilidade: descrição da reação ativa mais recente."""
        ativas = self.reacoes_ativas
        return ativas[-1].descricao if ativas else None

    def registrar_reacao(self, manifestacao: str, gravidade: str, descricao: str = None,
                          data_ocorrencia=None, criado_por: int = None,
                          id_atendimento_origem: int = None):
        """Adiciona uma nova reação ao histórico desta alergia, com quem
        registrou e o Atendimento de origem."""
        from src.models.pacientes.reacao_alergia import ReacaoAlergia
        self.reacoes.append(ReacaoAlergia(
            manifestacao=manifestacao,
            gravidade=gravidade,
            descricao=descricao,
            data_ocorrencia=data_ocorrencia,
            criado_por=criado_por,
            id_atendimento_origem=id_atendimento_origem,
        ))

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "substancia": self.substancia,
            "tipo_reacao": self.tipo_reacao,
            "gravidade": self.gravidade,
            "descricao_reacao": self.descricao_reacao,
            "flag_confirmado": self.flag_confirmado,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "criado_por": self.usuario_criacao.nome_completo if self.usuario_criacao else None,
            "atendimento_origem_uuid": self.atendimento_origem.uuid if self.atendimento_origem else None,
            "reacoes": [r.to_dict() for r in self.reacoes_ativas],
        }

    def __repr__(self):
        return f"<Alergia {self.uuid} [{self.substancia}]>"