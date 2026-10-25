"""
Dominio Catalogo.

Tabelas de referencia (nao-transacionais): catalogo de exames, catalogo
de medicamentos e interacoes conhecidas entre medicamentos. Eram stubs
no projeto original; completadas aqui.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class CatalogoExames(db.Model):
    __tablename__ = "catalogo_exames"

    id = db.Column("id_catalogo_exame",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_catalogo_exame",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome_exame = db.Column(db.String(255), nullable=False)
    nome_exame_en = db.Column(db.String(255))  # nome em inglês (interface bilíngue)
    codigo_tuss = db.Column(db.String(20))
    tipo = db.Column(db.Enum("laboratorial", "imagem", "funcional", "outro"))
    material = db.Column(db.String(100))
    material_en = db.Column(db.String(100))
    jejum_horas = db.Column(db.SmallInteger)
    observacoes = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)

    # Ligacao com a referencia LOINC e campos de busca do medico.
    # nome_exame e o nome CURADO que o medico ve; codigo_loinc e a chave tecnica.
    codigo_loinc = db.Column(db.String(10), db.ForeignKey("loinc_termo.loinc_num"))
    nome_normalizado = db.Column(db.String(255), unique=True)
    # nome pt | nome en | sinônimos, normalizados (busca do médico; preenchido pela importação)
    busca_normalizada = db.Column(db.Text)
    sinonimos_busca_json = db.Column(db.JSON)

    prescricoes_exame = db.relationship("PrescricaoExame", back_populates="catalogo_exame")
    termo_loinc = db.relationship("LoincTermo")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome_exame": self.nome_exame,
            "nome_exame_en": self.nome_exame_en,
            "codigo_tuss": self.codigo_tuss,
            "codigo_loinc": self.codigo_loinc,
            "tipo": self.tipo,
            "material": self.material,
            "material_en": self.material_en,
            "jejum_horas": self.jejum_horas,
            "ativo": self.ativo,
        }

    def to_dict_detalhe(self):
        d = self.to_dict()
        d["observacoes"] = self.observacoes
        d["sinonimos"] = self.sinonimos_busca_json
        return d

    def __repr__(self):
        return f"<CatalogoExames {self.uuid} [{self.nome_exame}]>"
