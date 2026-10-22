"""Metodos de busca de exames no catalogo. So leitura."""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .registro import Retorno, metodo
from .util import Limite, Termo, compacto_exame

TEXTO_MAX = 3000   # limite de caracteres do texto longo entregue a IA (corte em fronteira de secao)


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArgsExameNome(_Args):
    termo: Termo
    tipo: Literal["laboratorial", "imagem", "funcional", "outro"] | None = None
    limite: Limite = 10


class ArgsExameUuid(_Args):
    uuid_exame: str = Field(min_length=36, max_length=36)


@metodo("exame_por_nome",
        "Busca exames ativos do catalogo por nome (pt/en) ou sinonimo. Devolve uuid_exame.", ArgsExameNome)
def por_nome(ctx, a: ArgsExameNome) -> Retorno:
    dados = [compacto_exame(e) for e in ctx.exames.buscar_ativos(a.termo, a.tipo, a.limite)]
    uuids = frozenset(d["uuid_exame"] for d in dados)
    return Retorno(dados, exames=uuids, resumo={"n": len(dados), "uuids": sorted(uuids)})


@metodo("exame_detalhe", "Detalha um exame do catalogo (tipo, material, jejum, codigo LOINC).", ArgsExameUuid)
def detalhe(ctx, a: ArgsExameUuid) -> Retorno:
    e = ctx.exames.find_by_uuid(a.uuid_exame)
    if e is None or getattr(e, "ativo", True) is False:
        return Retorno({"erro": "exame nao encontrado ou inativo no catalogo"}, resumo={"n": 0})
    d = compacto_exame(e)
    return Retorno(d, exames=frozenset({d["uuid_exame"]}), resumo={"n": 1, "uuids": [d["uuid_exame"]]})


IDIOMAS_CONTEUDO = ("en", "es")   # idiomas guardados do MedlinePlus; outro cai em "en"


@metodo("exame_conteudo",
        "Texto educativo do exame (MedlinePlus): o que e, para que serve, preparo e resultados. "
        "Conteudo geral de base americana, nao protocolo brasileiro.", ArgsExameUuid)
def conteudo(ctx, a: ArgsExameUuid) -> Retorno:
    e = ctx.exames.find_by_uuid(a.uuid_exame)
    if e is None or getattr(e, "ativo", True) is False:
        return Retorno({"erro": "exame nao encontrado ou inativo no catalogo"}, resumo={"n": 0})
    curto = ctx.idioma.split("-")[0]
    c = ctx.exames_conteudo.contexto_para_ia(e.id, curto if curto in IDIOMAS_CONTEUDO else "en", TEXTO_MAX)
    if not c or not c.get("texto"):
        return Retorno({"erro": "sem conteudo para este exame"}, resumo={"n": 0})
    h = hashlib.sha256(c["texto"].encode("utf-8")).hexdigest()    # do texto que a IA realmente viu
    dados = {k: c.get(k) for k in ("texto", "fonte", "url", "idioma", "buscado_em")}
    return Retorno(dados, resumo={"n": 1, "uuid_exame": a.uuid_exame, "caracteres": len(c["texto"])}, hash_conteudo=h)
