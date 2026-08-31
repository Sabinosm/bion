"""Reexporta os blueprints do dominio Paciente para registro no app factory.

Prefixos (definidos no register_blueprint do app factory, não aqui):
  pessoal_bp        -> /v1/api/pacientes/pessoal
  p_clinico_bp       -> /v1/api/pacientes/clinico
  bp_alergia         -> /v1/api/pacientes/clinico
  bp_doenca_cronica  -> /v1/api/pacientes/clinico
  bp_med_em_uso      -> /v1/api/pacientes/clinico
  lgpd_bp            -> /v1/api/pacientes/lgpd  (prefixo PRÓPRIO -- ver lgpd_controller.py)
"""

from .paciente_pessoal_controller import bp as pessoal_bp
from .doenca_cronica_controller import bp as bp_doenca_cronica
from .alergia_controller import bp as bp_alergia
from .medicamentos_em_uso_controller import bp as bp_med_em_uso
from .lgpd_controller import bp as lgpd_bp
from .paciente_clinico_controller import bp as p_clinico_bp

__all__ = ["pessoal_bp", "bp_doenca_cronica", "lgpd_bp", "bp_alergia", "bp_med_em_uso", "p_clinico_bp"]