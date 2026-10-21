"""Validacao da resposta: estrutura (Pydantic) + referencias ao que a IA recebeu.

`interpretar` e o ponto de entrada: recebe a resposta crua da IA e devolve
ok/erros. Os erros ficam em texto, prontos para devolver a IA numa nova tentativa.
Nao registra o conteudo da resposta em log (pode conter dado do paciente).

Por que checar os uuids AQUI: registrar_proposta grava tudo numa transacao e
desfaz tudo se UM uuid nao existir. Um uuid copiado errado pela IA derrubaria a
proposta inteira; aqui vira um erro corrigivel numa nova tentativa.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Container
from dataclasses import dataclass, field
from typing import Iterable

from pydantic import ValidationError

from .schema import OutputIA

log = logging.getLogger(__name__)

# Antes de sugerir medicamento, a IA deve DECLARAR que considerou estes blocos.
# E so uma declaracao (rastreabilidade e gatilho de nova tentativa), nao prova
# de seguranca: a checagem clinica de verdade continua no codigo. So exige os
# que existem no input. Ajuste ou esvazie a tupla se nao fizer sentido.
BLOCOS_OBRIGATORIOS_PARA_MEDICAMENTO = ("paciente", "alergias", "medicamentos", "doenca_cronica")


@dataclass(frozen=True)
class Interpretacao:
    ok: bool
    output: OutputIA | None = None
    erros: list[str] = field(default_factory=list)


def _carregar(bruto):
    if isinstance(bruto, dict):
        return bruto
    if isinstance(bruto, (bytes, bytearray)):
        bruto = bruto.decode("utf-8", errors="replace")
    if not isinstance(bruto, str):
        raise TypeError("resposta nao e texto nem objeto")
    texto = bruto.strip()
    if texto.startswith("```"):  # tolera resposta embrulhada em ```json ... ```
        texto = re.sub(r"^```[A-Za-z]*\s*", "", texto)
        texto = re.sub(r"\s*```$", "", texto)
    return json.loads(texto)


def _formatar(ex: ValidationError) -> list[str]:
    saida = []
    for e in ex.errors():
        loc = ".".join(str(p) for p in e["loc"]) or "(raiz)"
        msg = e["msg"].removeprefix("Value error, ")
        saida += [f"{loc}: {linha}" for linha in msg.split("\n") if linha.strip()]
    return saida


def validar_contra_input(output: OutputIA, nomes_blocos: Iterable[str], *,
                         medicamentos_validos: Container[str] | None = None,
                         exames_validos: Container[str] | None = None) -> list[str]:
    """Confere que o output so cita o que a IA recebeu.

    - blocos: nomes que existem no input (InputModel.nomes()).
    - medicamentos_validos / exames_validos: uuids (em minuscula) que foram
      mostrados a IA nesta chamada. Qualquer colecao com `in` serve (set, objeto
      com __contains__). None = nao checa.
    """
    nomes = set(nomes_blocos)
    existentes = sorted(nomes)
    erros = []
    desconhecidos = [b for b in output.blocos_considerados if b not in nomes]
    if desconhecidos:
        erros.append(f"blocos_considerados: blocos inexistentes no input: {desconhecidos}. "
                     f"Use apenas: {existentes}.")
    for i, p in enumerate(output.perguntas_pendentes):
        if p.bloco_relacionado and p.bloco_relacionado not in nomes:
            erros.append(f"perguntas_pendentes.{i}.bloco_relacionado: "
                         f"bloco inexistente '{p.bloco_relacionado}'. Use apenas: {existentes}.")
    if output.proposta.medicamentos:
        faltam = [b for b in BLOCOS_OBRIGATORIOS_PARA_MEDICAMENTO
                  if b in nomes and b not in output.blocos_considerados]
        if faltam:
            erros.append(f"blocos_considerados: ao sugerir medicamento, considere tambem {faltam}.")
    if medicamentos_validos is not None:
        for i, m in enumerate(output.proposta.medicamentos):
            if m.uuid_catalogo not in medicamentos_validos:
                erros.append(f"proposta.medicamentos.{i}.uuid_catalogo: uuid '{m.uuid_catalogo}' nao esta "
                             "entre os medicamentos fornecidos. Use somente uuids do catalogo fornecido.")
    if exames_validos is not None:
        for i, x in enumerate(output.proposta.exames):
            if x.uuid_exame not in exames_validos:
                erros.append(f"proposta.exames.{i}.uuid_exame: uuid '{x.uuid_exame}' nao esta "
                             "entre os exames fornecidos. Use somente uuids do catalogo fornecido.")
    return erros


def interpretar(bruto, nomes_blocos: Iterable[str], *,
                medicamentos_validos: Container[str] | None = None,
                exames_validos: Container[str] | None = None) -> Interpretacao:
    """Resposta crua da IA (str, bytes ou dict) -> Interpretacao."""
    try:
        dados = _carregar(bruto)
    except (json.JSONDecodeError, TypeError):
        log.warning("resposta da IA rejeitada: nao e JSON")
        return Interpretacao(False, None, ["(raiz): a resposta nao e um JSON valido; "
                                           "devolva um unico objeto JSON no formato da casca."])
    try:
        output = OutputIA.model_validate(dados)
    except ValidationError as ex:
        erros = _formatar(ex)
        log.warning("resposta da IA rejeitada: %d erro(s) de estrutura", len(erros))
        return Interpretacao(False, None, erros)
    erros = validar_contra_input(output, nomes_blocos, medicamentos_validos=medicamentos_validos,
                                 exames_validos=exames_validos)
    if erros:
        log.warning("resposta da IA rejeitada: %d erro(s) de referencia", len(erros))
        return Interpretacao(False, None, erros)
    return Interpretacao(True, output, [])
