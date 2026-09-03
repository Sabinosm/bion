"""
Dominio Paciente.

SEM ALTERAÇÃO -- confirmado no SQL (07_doenca_cronica_migration.sql):
esta tabela já estava bem modelada, mapeamento para Condition é quase
1:1. Incluído aqui apenas para deixar o domínio completo, idêntico ao
original.
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
    # NOVO: soft delete -- dado clínico histórico não pode ser apagado
    # fisicamente (auditoria/LGPD/responsabilidade médica). `deletado`
    # é um campo separado do status clínico (ativa/em-remissao) de
    # propósito: um dos motivos de delete é 'solicitacao-paciente',
    # onde o registro em si continua clinicamente válido (o paciente só
    # pediu pra remover por privacidade) -- se "deletado" fosse um
    # valor do mesmo Enum de status, essa remoção apagaria também a
    # informação de se a doença estava ativa ou em remissão no momento,
    # o que pode importar depois numa auditoria/disputa. Boolean (não
    # timestamp) por pedido explícito: index simples, filtro direto em
    # queries (`deletado == False`); deletado_em abaixo continua tendo
    # o "quando".
    deletado = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    deletado_em = db.Column(db.DateTime(timezone=True), nullable=True)
    # NOVO: motivo estruturado do soft delete -- Enum em vez de texto
    # livre pra manter consistência em relatórios/auditoria futuros.
    # nullable pq só se aplica quando deletado_em não é nulo (não dá
    # pra forçar NOT NULL condicional só com db.Column; a garantia
    # "sempre vem junto" fica a cargo do service, não do schema).
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
    # NOVO: detalhe em texto livre do motivo do delete -- obrigatório
    # apenas quando motivo_delete='outro' (garantido pelo schema, não
    # aqui). Campo separado de `observacoes` (que é clínico, sobre a
    # doença em si) de propósito: não faz sentido sobrescrever a
    # observação clínica original com o motivo do delete.
    observacoes_delete = db.Column(db.Text, nullable=True)

    paciente = db.relationship("Paciente", back_populates="doencas")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "codigo_cid10": self.codigo_cid10,
            "descricao_cid10": self.descricao_cid10,
            "desde": self.desde.isoformat() if self.desde else None,
            "status": self.status,
            "observacoes": self.observacoes,
        }

    def __repr__(self):
        return f"<DoencaCronica {self.uuid} [{self.codigo_cid10}]>"