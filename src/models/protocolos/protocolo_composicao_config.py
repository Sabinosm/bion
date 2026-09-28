"""
Dominio de Protocolos / IA (motor de triagem e suporte a decisao).

Novo (migration 2026-09-28): configuracao de agregacao e gatilhos,
1:1 com ProtocoloVersao (PK = FK). Todo protocolo composto precisa de
uma linha aqui, mesmo com agregacao = 'nenhuma'.

regra_gatilho_json: quais modulos (por sigla) ficam "nao_aplicavel"
conforme a classificacao de um gatilho.
"""

from src.models import db


class ProtocoloComposicaoConfig(db.Model):
    __tablename__ = "protocolo_composicao_config"

    id_protocolo_versao = db.Column(db.BigInteger,
                                     db.ForeignKey("protocolo_versao.id_versao",
                                                   ondelete="CASCADE"),
                                     primary_key=True)
    agregacao = db.Column(
        db.Enum("nenhuma", "soma", "maximo", "pior_categoria", "any_flag"),
        nullable=False, default="nenhuma")
    regra_gatilho_json = db.Column(db.JSON)

    protocolo_versao = db.relationship("ProtocoloVersao", back_populates="composicao_config")

    def to_dict(self):
        return {
            "agregacao": self.agregacao,
            "regra_gatilho": self.regra_gatilho_json,
        }

    def __repr__(self):
        return f"<ProtocoloComposicaoConfig pv={self.id_protocolo_versao} [{self.agregacao}]>"