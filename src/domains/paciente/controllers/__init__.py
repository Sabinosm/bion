"""Reexporta os blueprints do dominio Paciente para registro no app factory."""

from .pessoal_controller import bp as pessoal_bp
from .clinico_controller import bp as clinico_bp
from .lgpd_controller import bp as lgpd_bp

__all__ = ["pessoal_bp", "clinico_bp", "lgpd_bp"]
