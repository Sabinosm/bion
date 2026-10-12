"""
Dominio Paciente.

ALTERADO (Bloco 2): histórico clínico completo, no mesmo molde de Alergia.

- Autoria: criado_por, id_atendimento_origem.
- Soft delete: deletado, deletado_em, motivo_delete, observacoes_delete,
  deletado_por, id_atendimento_delecao. `deletado` é "o registro nunca
  deveria ter existido / saiu da visão"; continua independente do status
  clínico (ativa | em-remissao).
- Encerramento (fechar + criar novo): mudar status, CID ou desde NÃO edita
  a linha. A linha vigente é FECHADA (encerrado_em, encerrado_por,
  id_atendimento_encerramento, id_substituida_por -> linha nova) e uma
  nova nasce com os valores revisados. Assim "estava ativa até o
  atendimento X, depois entrou em remissão" fica no banco, sem depender
  do log de auditoria.
- Vigente (aberta) = encerrado_em IS NULL AND deletado = False.
- Relationship com Paciente: sem delete-orphan nem cascade de delete
  (nada se apaga): passive_deletes="all" + FK ON DELETE RESTRICT.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class DoencaCronica(db.Model):
    __tablename__ = "doenca_cronica"

    __table_args__ = (
        db.Index("idx_doenca_cronica_deletado", "deletado"),
        db.Index("idx_doenca_cronica_paciente_deletado", "id_paciente", "deletado"),
        db.Index("idx_doenca_cronica_paciente_aberta", "id_paciente", "deletado", "encerrado_em"),
    )

    id = db.Column("id_doenca_cronica", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_doenca_cronica", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    codigo_cid10 = db.Column(db.String(10), nullable=False)
    descricao_cid10 = db.Column(db.String(255), nullable=False)
    desde = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum("ativa", "em-remissao"), nullable=False)
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    # NOVO (Bloco 2): autoria e atendimento de origem do registro.
    criado_por = db.Column(db.BigInteger,
                            db.ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"))
    id_atendimento_origem = db.Column(db.BigInteger,
                                       db.ForeignKey("atendimento.id_atendimento", ondelete="RESTRICT"))

    # NOVO (Bloco 2): encerramento por revisão (fechar + criar novo).
    encerrado_em = db.Column(db.DateTime(timezone=True), nullable=True)
    encerrado_por = db.Column(db.BigInteger,
                               db.ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"), nullable=True)
    id_atendimento_encerramento = db.Column(
        db.BigInteger, db.ForeignKey("atendimento.id_atendimento", ondelete="RESTRICT"), nullable=True)
    # Aponta para a linha que SUBSTITUIU esta (a revisão mais nova).
    id_substituida_por = db.Column(
        db.BigInteger, db.ForeignKey("doenca_cronica.id_doenca_cronica", ondelete="RESTRICT"),
        nullable=True)

    # Soft delete (ver docstring do módulo).
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
    # Detalhe do motivo do delete -- separado de `observacoes` (clínica).
    observacoes_delete = db.Column(db.Text, nullable=True)
    # NOVO (Bloco 2): quem removeu e em qual Atendimento.
    deletado_por = db.Column(db.BigInteger,
                              db.ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"), nullable=True)
    id_atendimento_delecao = db.Column(db.BigInteger,
                                        db.ForeignKey("atendimento.id_atendimento", ondelete="RESTRICT"),
                                        nullable=True)

    paciente = db.relationship("Paciente", back_populates="doencas")
    usuario_criacao = db.relationship("Usuario", foreign_keys=[criado_por])
    atendimento_origem = db.relationship("Atendimento", foreign_keys=[id_atendimento_origem])
    substituta = db.relationship(
        "DoencaCronica", foreign_keys=[id_substituida_por],
        remote_side="DoencaCronica.id", uselist=False,
    )

    @property
    def aberta(self) -> bool:
        """Vigente: não encerrada por revisão e não removida."""
        return self.encerrado_em is None and not self.deletado

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "codigo_cid10": self.codigo_cid10,
            "descricao_cid10": self.descricao_cid10,
            "desde": self.desde.isoformat() if self.desde else None,
            "status": self.status,
            "observacoes": self.observacoes,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "criado_por": self.usuario_criacao.nome_completo if self.usuario_criacao else None,
            "atendimento_origem_uuid": self.atendimento_origem.uuid if self.atendimento_origem else None,
            "encerrada": self.encerrado_em is not None,
            "encerrado_em": self.encerrado_em.isoformat() if self.encerrado_em else None,
            "substituida_por_uuid": self.substituta.uuid if self.substituta else None,
        }

    def __repr__(self):
        return f"<DoencaCronica {self.uuid} [{self.codigo_cid10}]>"