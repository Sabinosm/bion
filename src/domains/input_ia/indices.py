"""Indices de qualidade do input: completude e confianca. Vao para
OutputBion.indice_completude e OutputBion.indice_confianca (0 a 100).

COMPLETUDE: quanto dos dados esperados esta presente.
  Cada bloco aplicavel tem uma fracao presentes/esperados (alergias: 1 item;
  paciente: idade, peso e altura; sinais vitais: os 7 tipos; protocolo: os campos
  do input). A completude e a MEDIA SIMPLES dessas fracoes, em %. "Paciente nega"
  conta como resposta completa. Blocos informativos ou que nao se aplicam ao tipo
  de atendimento ficam de fora.

CONFIANCA: quanto os dados PRESENTES merecem confianca (nao mede o que falta e
  nao e a confianca da IA). Parte de 100 e desconta, por ocorrencia, os sinais de
  baixa confiabilidade que os blocos emitem (ver Sinal em nucleo.py). Sem nenhum
  dado presente nao ha o que avaliar: None. Os motivos acompanham o numero.

>>> OS PESOS ABAIXO SAO PROVISORIOS: sao julgamento clinico e devem ser revistos
>>> por quem responde pela clinica antes de uso real.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .nucleo import Bloco, Sinal

PESOS_CONFIANCA: dict[str, float] = {
    Sinal.BINARIO_DIVERGE: 10,
    Sinal.DADO_CRITICO_AUSENTE: 8,
    Sinal.PROTOCOLO_INCOMPLETO: 8,
    Sinal.MEDICAMENTO_SEM_CATALOGO: 5,
    Sinal.SINAL_VITAL_FORA_DO_LIMITE: 5,
    Sinal.CONFERENCIA_PENDENTE: 4,
    Sinal.ALERGIA_NAO_CONFIRMADA: 3,
}


@dataclass(frozen=True)
class Indices:
    completude: float | None
    confianca: float | None
    completude_por_bloco: dict[str, float] = field(default_factory=dict)
    motivos_confianca: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"completude": self.completude, "confianca": self.confianca,
                "completude_por_bloco": dict(self.completude_por_bloco),
                "motivos_confianca": [dict(m) for m in self.motivos_confianca]}


def calcular(blocos: Iterable[Bloco]) -> Indices:
    blocos = list(blocos)

    por_bloco = {b.nome: b.presentes / b.esperados for b in blocos if b.esperados > 0}
    completude = round(100 * sum(por_bloco.values()) / len(por_bloco), 2) if por_bloco else None

    motivos = []
    for b in blocos:
        for codigo in dict.fromkeys(b.sinais):
            if codigo not in PESOS_CONFIANCA:
                raise ValueError(f"bloco '{b.nome}' emitiu sinal sem peso definido: {codigo!r}")
            n = b.sinais.count(codigo)
            motivos.append({"bloco": b.nome, "codigo": codigo, "ocorrencias": n,
                            "penalidade": PESOS_CONFIANCA[codigo] * n})
    motivos.sort(key=lambda m: (-m["penalidade"], m["bloco"], m["codigo"]))

    if sum(b.presentes for b in blocos if b.esperados > 0) == 0:
        confianca = None
    else:
        confianca = round(max(0.0, 100 - sum(m["penalidade"] for m in motivos)), 2)

    return Indices(completude, confianca,
                   {n: round(100 * f, 2) for n, f in por_bloco.items()}, motivos)