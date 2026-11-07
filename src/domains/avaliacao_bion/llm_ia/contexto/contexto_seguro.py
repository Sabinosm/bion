"""contexto_seguro.py

Porta única do dado clínico que chega à IA na avaliação. Valida o snapshot congelado em
OutputBion.input_ia_json, mascara identificadores (CPF, CNPJ, RG, e-mail, telefone, CEP, URL), limita o
tamanho do que segue e entrega o texto no formato de blocos "## nome" que o prompt de prescrição espera.

Dado nunca vira instrução nem estrutura: quebras de linha e separadores Unicode dentro de valores, chaves
e lacunas viram espaço, e chaves não podem começar com marcas de cabeçalho ou de lista; assim um texto livre
(queixa, observações, resultado de protocolo, histórico) não consegue forjar um bloco "## protocolo" nem uma
linha de instrução. Os estados informado, paciente_nega e nao_informado e as lacunas vêm prontos do snapshot
e são preservados como estão. Todos os blocos do snapshot seguem, inclusive o histórico de atendimentos e os
protocolos de referência; só o nome do bloco é validado, pois o texto depende dele.

Texto idêntico ao formato anterior para qualquer snapshot sem quebras de linha, separadores ou marcas de
estrutura dentro dos valores.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.domains.input_ia.nucleo import linhas
from src.domains.avaliacao_bion.llm_ia.sanitizer import limpar_estrutura

IDIOMA_PADRAO = "pt-BR"
MAXIMO_BLOCOS = 50

_NOME_BLOCO = re.compile(r"^[a-z][a-z0-9_]{0,59}$")
_IDIOMA = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
_QUEBRAS = re.compile(r"\s*[\r\n\u0085  ]+\s*")
_MARCAS_DE_ESTRUTURA = re.compile(r"^[\s#>*\-]+")


class SnapshotInvalidoError(ValueError):
    """Snapshot ausente, malformado ou fora dos limites. Nunca carrega conteúdo clínico na mensagem."""


@dataclass(frozen=True)
class BlocoSeguro:
    nome: str
    dados: dict


@dataclass(frozen=True)
class ContextoSeguro:
    idioma: str
    lacunas: tuple[str, ...]
    blocos: tuple[BlocoSeguro, ...]

    @property
    def nomes(self) -> list[str]:
        return [b.nome for b in self.blocos]

    @classmethod
    def de_snapshot(cls, snapshot: Any) -> "ContextoSeguro":
        if not isinstance(snapshot, dict):
            raise SnapshotInvalidoError("snapshot clinico invalido")
        contexto = snapshot.get("contexto")
        if not isinstance(contexto, dict) or not contexto:
            raise SnapshotInvalidoError("snapshot sem contexto clinico")
        if len(contexto) > MAXIMO_BLOCOS:
            raise SnapshotInvalidoError("snapshot com blocos demais")

        idioma = snapshot.get("idioma_resposta")
        idioma = idioma if isinstance(idioma, str) and _IDIOMA.match(idioma) else IDIOMA_PADRAO

        faltando = snapshot.get("faltando", [])
        if not isinstance(faltando, list) or not all(isinstance(x, str) for x in faltando):
            raise SnapshotInvalidoError("lista de lacunas do snapshot invalida")
        lacunas = tuple(_em_uma_linha(x) for x in limpar_estrutura(faltando))

        blocos = []
        for nome, dados in contexto.items():
            if not isinstance(nome, str) or not _NOME_BLOCO.match(nome) or not isinstance(dados, dict):
                raise SnapshotInvalidoError("bloco do snapshot invalido")
            blocos.append(BlocoSeguro(nome, _achatar(limpar_estrutura(dados))))
        return cls(idioma, lacunas, tuple(blocos))

    def para_prompt(self) -> str:
        partes = [f"idioma_resposta: {self.idioma}"]
        if self.lacunas:
            partes.append("## lacunas\n" + "\n".join(f"- {x}" for x in self.lacunas))
        for b in self.blocos:
            partes.append("\n".join([f"## {b.nome}", *linhas(b.dados)]))
        return "\n\n".join(partes)


def _em_uma_linha(texto: str) -> str:
    return _QUEBRAS.sub(" ", texto)


def _chave(chave: Any) -> str:
    limpa = _MARCAS_DE_ESTRUTURA.sub("", _em_uma_linha(str(chave)))
    return limpa or "_"


def _achatar(valor: Any) -> Any:
    if isinstance(valor, str):
        return _em_uma_linha(valor)
    if isinstance(valor, dict):
        saida: dict = {}
        for k, v in valor.items():
            chave = _chave(k)
            while chave in saida:                       # chaves que colidem após a limpeza não se sobrescrevem
                chave += "_"
            saida[chave] = _achatar(v)
        return saida
    if isinstance(valor, list):
        return [_achatar(x) for x in valor]
    return valor
