"""Reexporta os blueprints do dominio Paciente para registro no app factory."""

from .paciente_pessoal_controller import bp as pessoal_bp
from .doenca_cronica_service import bp as bp_doenca_cronica
from .alergia_controller import bp as bp_alergia
from  .medicamentos_em_uso_controller import bp as bp_med_em_uso
from .lgpd_controller import bp as lgpd_bp

__all__ = ["pessoal_bp", "bp_doenca_cronica", "lgpd_bp", "bp_alergia", "bp_med_em_uso"]
