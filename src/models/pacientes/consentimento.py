from datetime import datetime, timezone
import uuid as _uuid

from sqlalchemy.dialects.mysql import TINYINT, MEDIUMBLOB

from src.models import db
from src.models.types import BigIntPK


class Consentimento(db.Model):
    __tablename__ = "consentimento_lgpd"
    __table_args__ = (
        db.UniqueConstraint("id_paciente", "ativo_unico", name="uq_consentimento_ativo_paciente"),
    )

    id = db.Column("id_consentimento", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_consentimento",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    id_paciente = db.Column(db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    coletado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    versao_termo = db.Column(db.String(50), nullable=False)
    data_consentimento = db.Column(db.DateTime(timezone=True), nullable=False)
    canal_coleta = db.Column(
        db.Enum(
            "presencial-papel",
            "presencial-digital",
            "portal-online",
            "totem",
            "dispensa-emergencia",
        ),
        nullable=False,
    )
    status = db.Column(
        db.Enum("ativo", "revogado", "expirado", "dispensado_emergencia"),
        nullable=False,
        default="ativo",
    )
    escopo_consentimento_json = db.Column(db.JSON)
    data_revogacao = db.Column(db.DateTime(timezone=True))
    observacao = db.Column("observacao", db.Text)
    hash_documento = db.Column(db.String(64))
    assinatura_png = db.deferred(db.Column(MEDIUMBLOB, nullable=True))
    ativo_unico = db.Column(TINYINT, db.Computed("IF(status = 'ativo', 1, NULL)", persisted=True))
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    paciente = db.relationship("Paciente", back_populates="consentimentos")

    def _resumo_escopos(self):
        j = (
            self.escopo_consentimento_json
            if isinstance(self.escopo_consentimento_json, dict)
            else {}
        )
        aceitos = j.get("escopo") if isinstance(j.get("escopo"), list) else []
        oferecidos = j.get("escopos_oferecidos")
        if not isinstance(oferecidos, list) or not oferecidos:
            return aceitos, None
        return aceitos, [e for e in oferecidos if e not in aceitos]

    def to_dict(self):
        aceitos, recusados = self._resumo_escopos()
        return {
            "uuid": self.uuid,
            "versao_termo": self.versao_termo,
            "data_consentimento": (
                self.data_consentimento.isoformat() if self.data_consentimento else None
            ),
            "canal_coleta": self.canal_coleta,
            "status": self.status,
            "data_revogacao": self.data_revogacao.isoformat() if self.data_revogacao else None,
            "observacao": self.observacao,
            "escopos_aceitos": aceitos,
            "escopos_recusados": recusados,
            "possui_pdf": self.canal_coleta == "presencial-digital",
            "pdf_url": (
                f"/v1/api/pacientes/lgpd/download-pdf/{self.uuid}"
                if self.canal_coleta == "presencial-digital"
                else None
            ),
        }

    def __repr__(self):
        return f"<Consentimento {self.uuid} [{self.status}]>"
