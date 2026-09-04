"""
Dominio de Auditoria.

Logs imutaveis de acesso e de alteracao (trilha de auditoria), essenciais
para conformidade LGPD e rastreabilidade. Nao existiam como classes no
projeto original -- criados aqui com os campos do schema.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK



class LogAlteracao(db.Model):
    __tablename__ = "log_alteracao"

    id = db.Column("id_alteracao",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_alteracao",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"), nullable=False)
    # Identificador de acao de negocio, ex: "editar_paciente",
    # "visualizar_paciente" -- o mesmo valor ja usado manualmente no
    # parametro `acao` de @acao_sensivel(acao, tabela=...). Texto livre
    # por enquanto (sem Enum): a lista de valores ainda nao esta fechada,
    # entao travar em Enum agora so geraria migracao toda vez que uma
    # acao nova surgisse. Migrar para Enum quando o vocabulario estabilizar.
    acao = db.Column(db.String(100))
    tabela_origem = db.Column(db.String(100), nullable=False)
    id_registro = db.Column(db.BigInteger, nullable=False)
    uuid_registro = db.Column(db.String(36), nullable=False)
    operacao = db.Column(db.Enum("INSERT", "UPDATE", "DELETE"), nullable=False)
    campo_alterado = db.Column(db.String(100))
    valor_anterior = db.Column(db.Text)
    valor_novo = db.Column(db.Text)
    alterado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    ip_origem = db.Column(db.String(45))
    justificativa = db.Column(db.Text)
    alterado_em = db.Column(db.DateTime(timezone=True),
                             default=lambda: datetime.now(timezone.utc), nullable=False)

    usuario = db.relationship("Usuario")
    empresa = db.relationship("Empresa")

    __table_args__ = (
        # Filtro 1 (empresa) + Filtro 4 (janela de data deslizante)
        db.Index("ix_log_alteracao_empresa_data", "id_empresa", "alterado_em"),
        # Filtro 2/3 (drill-down por usuario, mais recentes primeiro)
        db.Index("ix_log_alteracao_usuario_data", "alterado_por", "alterado_em"),
        # drill-down por registro alterado (ja usado em find_por_registro)
        db.Index("ix_log_alteracao_registro_data", "uuid_registro", "alterado_em"),
        # Filtro por acao (nova tela de pesquisa) + empresa
        db.Index("ix_log_alteracao_empresa_acao", "id_empresa", "acao"),
    )

    def to_dict(self):
        """Serializacao completa -- usar no drill-down (Filtro 3/4), inclui o diff.

        Inclui justificativa: agora obrigatoria em DELETE (ver service),
        entao faz parte do que se espera ver no detalhe de uma exclusao.
        """
        return {
            "uuid": self.uuid,
            "acao": self.acao,
            "tabela_origem": self.tabela_origem,
            "operacao": self.operacao,
            "campo_alterado": self.campo_alterado,
            "valor_anterior": self.valor_anterior,
            "valor_novo": self.valor_novo,
            "justificativa": self.justificativa,
            "alterado_em": self.alterado_em.isoformat() if self.alterado_em else None,
        }

    def to_dict_resumido(self):
        """Serializacao enxuta -- usar na lista resumida por usuario (Filtro 2:
        'ultimas 3 alteracoes', so frase de acao + data, sem o diff completo).
        Nome/cargo do usuario vem via join com Usuario, nao daqui.

        Prioriza `acao` (mais legivel, ex: "editar_paciente") quando
        disponivel; cai para "operacao em tabela.campo" como fallback
        para logs antigos gravados antes desta coluna existir.
        """
        frase_acao = self.acao or (
            f"{self.operacao} em {self.tabela_origem}"
            + (f".{self.campo_alterado}" if self.campo_alterado else "")
        )
        return {
            "uuid": self.uuid,
            "frase_acao": frase_acao,
            "data_hora": self.alterado_em.isoformat() if self.alterado_em else None,
        }

    def __repr__(self):
        return f"<LogAlteracao {self.uuid} [{self.acao or self.operacao} em {self.tabela_origem}]>"