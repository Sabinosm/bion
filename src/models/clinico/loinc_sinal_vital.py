"""
LoincSinalVital — tabela de referência com códigos LOINC/UCUM oficiais,
confirmados diretamente na spec: https://www.hl7.org/fhir/observation-vitalsigns.html
"""

from src.models import db


class LoincSinalVital(db.Model):
    __tablename__ = "loinc_sinal_vital"

    tipo_parametro = db.Column(db.String(40), primary_key=True)
    codigo_loinc = db.Column(db.String(20), nullable=False)
    display_loinc = db.Column(db.String(150), nullable=False)
    unidade_ucum = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f"<LoincSinalVital {self.tipo_parametro} -> {self.codigo_loinc}>"
