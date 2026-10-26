"""Este arquivo converte o resultado de um protocolo determinístico (dict ou dataclass do host) em ResultadoTriagemSeguro."""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Mapping, Optional

from src.core.exceptions import DadosInvalidosError

from .clinical_context import ResultadoTriagemSeguro
from .sanitizer import texto_opcional

CAMPOS_CONHECIDOS = {
    "protocolo", "versao_protocolo", "versao", "cor_mts", "tempo_max_espera",
    "tempo_max_espera_minutos", "discriminante_determinante", "score_news2",
    "nivel_risco_news2", "alertas",
}
CAMPOS_IGNORADOS = {"discriminadores_avaliados", "subscores_news2"}


def _inteiro(valor: Any, campo: str, minimo: int, maximo: int) -> Optional[int]:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or (
        isinstance(valor, float) and not math.isfinite(valor)
    ):
        raise DadosInvalidosError(f"resultado_triagem.{campo} deve ser numérico.", campo="resultado_triagem")
    inteiro = int(valor)
    if inteiro != valor or not minimo <= inteiro <= maximo:
        raise DadosInvalidosError(
            f"resultado_triagem.{campo} fora do intervalo {minimo}-{maximo}.", campo="resultado_triagem"
        )
    return inteiro


def de_resultado_deterministico(resultado: Any) -> Optional[ResultadoTriagemSeguro]:
    """Esta função aceita o ResultadoTriagem do host (dataclass) ou um dict equivalente e devolve o resultado seguro.

    Chaves desconhecidas são rejeitadas pelo nome, sem ecoar valores.
    """
    if resultado is None:
        return None
    if dataclasses.is_dataclass(resultado) and not isinstance(resultado, type):
        dados: Mapping[str, Any] = dataclasses.asdict(resultado)
    elif isinstance(resultado, Mapping):
        dados = resultado
    else:
        raise DadosInvalidosError("resultado_triagem deve ser um objeto.", campo="resultado_triagem")
    if not dados:
        return None

    desconhecidas = sorted(str(k) for k in dados if k not in CAMPOS_CONHECIDOS and k not in CAMPOS_IGNORADOS)
    if desconhecidas:
        raise DadosInvalidosError(
            f"resultado_triagem contém campos não aceitos: {', '.join(desconhecidas)}.",
            campo="resultado_triagem",
        )

    alertas_brutos = dados.get("alertas") or []
    if not isinstance(alertas_brutos, (list, tuple)):
        raise DadosInvalidosError("resultado_triagem.alertas deve ser uma lista.", campo="resultado_triagem")
    alertas = tuple(a for a in (texto_opcional(x, 300) for x in alertas_brutos[:20]) if a)

    tempo = dados.get("tempo_max_espera_minutos")
    if tempo is None:
        tempo = dados.get("tempo_max_espera")

    return ResultadoTriagemSeguro(
        protocolo=texto_opcional(dados.get("protocolo"), 50),
        versao_protocolo=texto_opcional(dados.get("versao_protocolo") or dados.get("versao"), 50),
        cor_mts=texto_opcional(dados.get("cor_mts"), 30),
        tempo_max_espera_minutos=_inteiro(tempo, "tempo_max_espera", 0, 1440),
        discriminante_determinante=texto_opcional(dados.get("discriminante_determinante"), 200),
        score_news2=_inteiro(dados.get("score_news2"), "score_news2", 0, 20),
        nivel_risco_news2=texto_opcional(dados.get("nivel_risco_news2"), 50),
        alertas=alertas,
    )
