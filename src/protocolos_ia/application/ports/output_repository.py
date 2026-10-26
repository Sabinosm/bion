"""Este arquivo define o contrato de persistência do envio à IA e do registro da resposta."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol


@dataclass(frozen=True)
class AutorRequisicao:
    """Usuário autenticado que originou a requisição. Vem sempre da sessão, nunca do corpo."""

    id_usuario: int
    funcao_clinica: Optional[str]
    id_empresa: int


@dataclass(frozen=True)
class EnvioAberto:
    """Envio já registrado, com o snapshot clínico congelado. handle é opaco para o caso de uso."""

    uuid: str
    snapshot: dict
    versao_input_model: Optional[int]
    criado_em: Optional[str]
    handle: Any = None


@dataclass(frozen=True)
class RegistroGravado:
    uuid: str
    versao_input_model: Optional[int]
    criado_em: Optional[str]
    indice_completude: Optional[float] = None
    indice_confianca: Optional[float] = None


class OutputRepository(Protocol):
    def abrir_envio(self, id_input_protocolo: int, autor: AutorRequisicao) -> EnvioAberto:
        ...

    def gravar_resposta(self, envio: EnvioAberto, output_ia: dict, versao_modelo_ia: str) -> RegistroGravado:
        ...
