"""Pacote paciente_service.

Mantém o import antigo funcionando:
    from src.domains.paciente.services.paciente_service import PacienteService
"""
from .service import PacienteService
from .helpers import _normalizar, _parse_data, _CONSTRAINT_CPF_EMPRESA, _violou_cpf_unico

__all__ = [
    "PacienteService",
    "_normalizar",
    "_parse_data",
    "_CONSTRAINT_CPF_EMPRESA",
    "_violou_cpf_unico",
]
