"""
PapelProfissional — espelha o PractitionerRole do FHIR.

Extrai o que antes era atributos_profissionais_json (JSON solto) e
tipo_usuario (enum em Usuario) para uma tabela própria e estruturada.

DECISÃO (Opção B, confirmada com o usuário): tipo_usuario SAI de Usuario
por completo. A autorização de rota, que antes lia session["tipo_usuario"]
direto, passa a ser calculada no momento do LOGIN via papel_ativo,
e cacheada na sessão exatamente como antes — nenhuma mudança de
comportamento perceptível, e sem custo de performance em runtime
(o join só acontece uma vez, no login).
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class PapelProfissional(db.Model):
    __tablename__ = "papel_profissional"

    __table_args__ = (
        db.Index('ix_papel_usuario_tipo_ativo',
                  'id_usuario', 'tipo_papel', 'ativo'),
        # ajuda o JOIN por id_usuario e evita filesort no GROUP BY tipo_papel de A4
    )
    
    id = db.Column("id_papel_profissional", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_papel_profissional", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_usuario = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)

    tipo_papel = db.Column(db.Enum("medico", "enfermeiro"), nullable=False)
    numero_conselho = db.Column(db.String(20), nullable=False)
    uf_conselho = db.Column(db.String(2), nullable=False)
    especialidade = db.Column(db.String(100), nullable=True)  # só enfermeiro usa hoje
    rqe = db.Column(db.String(20), nullable=True)              # só médico usa hoje

    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    usuario = db.relationship("Usuario", back_populates="papeis")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_papel": self.tipo_papel,
            "numero_conselho": self.numero_conselho,
            "uf_conselho": self.uf_conselho,
            "especialidade": self.especialidade,
            "rqe": self.rqe,
            "ativo": self.ativo,
        }
