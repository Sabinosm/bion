"""
ReacaoAlergia — espelha AllergyIntolerance.reaction[] do FHIR (lista).

Extraído de Alergia: tipo_reacao e gravidade se sobrepunham no schema
antigo (ex: 'anafilaxia' aparecia nos dois enums). Agora cada reação
é uma linha própria, permitindo múltiplas reações por alergia ao
longo do tempo -- o que o FHIR já modela dessa forma.
"""

from src.models import db
from src.models.types import BigIntPK
import uuid as _uuid


class ReacaoAlergia(db.Model):
    __tablename__ = "reacao_alergia"

    id = db.Column("id_reacao", BigIntPK, primary_key=True, autoincrement=True)
    # ALTERADO: faltava default -- coluna NOT NULL sem valor gerado
    # automaticamente quebrava (IntegrityError) todo insert de reação,
    # inclusive o fluxo normal de Alergia.registrar_reacao(), que nunca
    # passa uuid manualmente. Mesmo padrão dos outros models do domínio.
    uuid = db.Column("uuid_reacao", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_alergia = db.Column(db.BigInteger, db.ForeignKey("alergia.id_alergia"), nullable=False)
    manifestacao = db.Column(
        db.Enum("cutanea", "respiratoria", "anafilaxia", "gastrointestinal",
                "cardiovascular", "sistemica"),
        nullable=False)
    # 'anafilaxia' REMOVIDA das opções de gravidade -- já é uma manifestacao,
    # não deveria competir como categoria de severidade também
    gravidade = db.Column(db.Enum("leve", "moderada", "grave"), nullable=False)
    descricao = db.Column(db.Text)
    data_ocorrencia = db.Column(db.Date, nullable=True)

    alergia = db.relationship("Alergia", back_populates="reacoes")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "manifestacao": self.manifestacao,
            "gravidade": self.gravidade,
            "descricao": self.descricao,
            "data_ocorrencia": self.data_ocorrencia.isoformat() if self.data_ocorrencia else None,
        }

    def __repr__(self):
        return f"<ReacaoAlergia {self.uuid} [{self.manifestacao}]>"