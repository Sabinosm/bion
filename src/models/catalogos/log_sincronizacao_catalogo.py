"""
Dominio Catalogo (medicamentos).

Registro de cada alteração aplicada pelo processo automático de
sincronização do catálogo (ver atualizacao_medicamentos_service.py).
Uma linha por medicamento alterado/criado em cada rodada -- é o que
sustenta "o que foi alterado" quando o job aplica atualização sozinho,
sem revisão humana prévia.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class LogSincronizacaoCatalogo(db.Model):
    __tablename__ = "log_sincronizacao_catalogo"
    __table_args__ = (
        # id_catalogo já ganha índice automático por ser FOREIGN KEY.
        db.Index("idx_log_sync_executado_em", "executado_em"),
    )

    id = db.Column("id_log_sincronizacao", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_log_sincronizacao", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_catalogo = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"),
                             nullable=False)
    tipo_alteracao = db.Column(db.Enum("criado", "atualizado"), nullable=False)
    fonte = db.Column(db.String(255), nullable=False)
    dados_antes_json = db.Column(db.JSON)  # null quando tipo_alteracao == "criado"
    dados_depois_json = db.Column(db.JSON, nullable=False)
    executado_em = db.Column(db.DateTime(timezone=True), nullable=False,
                              default=lambda: datetime.now(timezone.utc))

    catalogo_medicamentos = db.relationship("CatalogoMedicamentos")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_alteracao": self.tipo_alteracao,
            "fonte": self.fonte,
            "dados_antes": self.dados_antes_json,
            "dados_depois": self.dados_depois_json,
            "executado_em": self.executado_em.isoformat() if self.executado_em else None,
        }

    def __repr__(self):
        return f"<LogSincronizacaoCatalogo {self.uuid} [{self.tipo_alteracao}]>"