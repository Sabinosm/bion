"""Prepara JSON Schemas (Pydantic) para o Gemini: resolve $ref/$defs, tira o que ele
ignora ou rejeita e escreve anyOf-com-null como type com lista. A validacao de verdade
continua sendo a do Pydantic (interpretar); o esquema enviado so orienta o modelo."""
from __future__ import annotations

from copy import deepcopy

# chaves que o Gemini nao enforca ou nao aceita; o Pydantic as valida depois
_REMOVER = {"title", "default", "minLength", "maxLength", "pattern", "format", "examples", "$defs", "definitions"}


def _resolver(no, defs):
    if isinstance(no, dict):
        if "$ref" in no:
            alvo = defs[no["$ref"].rsplit("/", 1)[-1]]
            resto = {k: v for k, v in no.items() if k != "$ref"}
            return _resolver({**alvo, **resto}, defs)
        return {k: _resolver(v, defs) for k, v in no.items()}
    if isinstance(no, list):
        return [_resolver(x, defs) for x in no]
    return no


def _limpar(no):
    if isinstance(no, list):
        return [_limpar(x) for x in no]
    if not isinstance(no, dict):
        return no
    out = {k: _limpar(v) for k, v in no.items() if k not in _REMOVER}
    # anyOf: [X, {type: null}]  ->  X com type [.., "null"]
    alts = out.get("anyOf")
    if isinstance(alts, list):
        nao_nulos = [a for a in alts if a.get("type") != "null"]
        if len(nao_nulos) == 1 and len(alts) == 2 and isinstance(nao_nulos[0].get("type"), str):
            base = {**nao_nulos[0], **{k: v for k, v in out.items() if k != "anyOf"}}
            base["type"] = [base["type"], "null"]
            return base
    # propriedades: mantem os nomes (nao confundir uma propriedade chamada "title" com a chave)
    if isinstance(out.get("properties"), dict) and isinstance(no.get("properties"), dict):
        out["properties"] = {k: _limpar(v) for k, v in no["properties"].items()}
    return out


def para_gemini(schema: dict) -> dict:
    s = deepcopy(schema)
    defs = {**s.get("$defs", {}), **s.get("definitions", {})}
    return _limpar(_resolver(s, defs))
