from src.models import db


class ProtocoloComposicaoConfig(db.Model):
    __tablename__ = "protocolo_composicao_config"

    id_protocolo_versao = db.Column(
        db.BigInteger,
        db.ForeignKey("protocolo_versao.id_versao", ondelete="CASCADE"),
        primary_key=True,
    )
    agregacao = db.Column(
        db.Enum("nenhuma", "soma", "maximo", "pior_categoria", "any_flag"),
        nullable=False,
        default="nenhuma",
    )
    regra_gatilho_json = db.Column(db.JSON)

    protocolo_versao = db.relationship("ProtocoloVersao", back_populates="composicao_config")

    def to_dict(self):
        return {
            "agregacao": self.agregacao,
            "regra_gatilho": self.regra_gatilho_json,
        }

    def __repr__(self):
        return f"<ProtocoloComposicaoConfig pv={self.id_protocolo_versao} [{self.agregacao}]>"
