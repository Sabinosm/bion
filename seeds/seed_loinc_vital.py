"""Seed idempotente da tabela loinc_sinal_vital."""
from src.models import db
from src.models.clinico import LoincSinalVital

# tipo_parametro tem de ser idêntico ao Literal TipoParametro do schema.py
LOINC_SINAIS = [
    ("frequencia-respiratoria", "9279-1",  "Respiratory rate", "/min"),
    ("spo2",                    "59408-5", "Oxygen saturation in Arterial blood by Pulse oximetry", "%"),
    ("pa-sistolica",            "8480-6",  "Systolic blood pressure", "mm[Hg]"),
    ("pa-diastolica",           "8462-4",  "Diastolic blood pressure", "mm[Hg]"),
    ("frequencia-cardiaca",     "8867-4",  "Heart rate", "/min"),
    ("temperatura",             "8310-5",  "Body temperature", "Cel"),
    ("glicemia-capilar",        "2339-0",  "Glucose [Mass/volume] in Blood", "mg/dL"),
]


def seed() -> int:
    try:
        for tipo, codigo, display, ucum in LOINC_SINAIS:
            db.session.merge(LoincSinalVital(
                tipo_parametro=tipo,
                codigo_loinc=codigo,
                display_loinc=display,
                unidade_ucum=ucum,
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return len(LOINC_SINAIS)