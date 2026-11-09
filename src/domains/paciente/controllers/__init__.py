"""__init__.py

Reexporta os blueprints do domínio Paciente para registro no app factory. Os nomes
históricos foram mantidos (pessoal_bp, p_clinico_bp, bp_med_em_uso, lgpd_bp,
consentimento_digital_bp), e os blueprints de escrita e de tipo sanguíneo foram
acrescentados.

Prefixos (definidos no register_blueprint do app factory, não aqui):
  pessoal_bp                -> /v1/api/pacientes/pessoal
  p_clinico_bp              -> /v1/api/pacientes/clinico
  bp_alergia                -> /v1/api/pacientes/clinico
  bp_doenca_cronica         -> /v1/api/pacientes/clinico
  bp_med_em_uso             -> /v1/api/pacientes/clinico
  bp_tipo_sanguineo         -> /v1/api/pacientes/clinico
  lgpd_bp                   -> /v1/api/pacientes/lgpd  (prefixo PRÓPRIO: ver lgpd_controller.py)
  consentimento_digital_bp  -> /v1/api/pacientes/lgpd  (mesmo prefixo do lgpd_bp)

Os blueprints `*_escrita` são aninhados no atendimento (/<uuid_atendimento>/pacientes/...) e
devem ser registrados com o MESMO url_prefix do blueprint de atendimento.
"""

from .paciente_pessoal_controller import bp as pessoal_bp
from .doenca_cronica_controller import bp as bp_doenca_cronica, bp_escrita as bp_doenca_cronica_escrita
from .alergia_controller import bp as bp_alergia, bp_escrita as bp_alergia_escrita
from .medicamentos_em_uso_controller import bp as bp_med_em_uso, bp_escrita as bp_med_em_uso_escrita
from .obs_tipo_sanguineo_controller import bp as bp_tipo_sanguineo, bp_escrita as bp_tipo_sanguineo_escrita
from .lgpd_controller import bp as lgpd_bp
from .paciente_clinico_controller import bp as p_clinico_bp
from .consentimento_digital_controller import bp as consentimento_digital_bp

__all__ = [
    "pessoal_bp",
    "bp_doenca_cronica",
    "bp_doenca_cronica_escrita",
    "lgpd_bp",
    "bp_alergia",
    "bp_alergia_escrita",
    "bp_med_em_uso",
    "bp_med_em_uso_escrita",
    "bp_tipo_sanguineo",
    "bp_tipo_sanguineo_escrita",
    "p_clinico_bp",
    "consentimento_digital_bp",
]
