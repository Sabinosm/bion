"""Unico ponto que importa os models do projeto. >>> AJUSTE os caminhos <<<
(Atendimento/ResultadoPrescricao vem de src.models.clinico, como nos seus services)."""
from src.models import db  # noqa: F401
from src.models.clinico import Atendimento, Consulta, ResultadoPrescricao  # noqa: F401
from src.models.protocolos import OutputBion  # noqa: F401  <- ajuste: onde mora OutputBion
