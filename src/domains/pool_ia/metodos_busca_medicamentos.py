"""Metodos de busca de medicamentos no catalogo. So leitura."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .registro import Retorno, metodo
from .util import Limite, Termo, compacto_interacao, compacto_med


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArgsTermo(_Args):
    termo: Termo
    limite: Limite = 10


class ArgsUuid(_Args):
    uuid_catalogo: str = Field(min_length=36, max_length=36)


def _lista(itens) -> Retorno:
    dados = [compacto_med(m) for m in itens]
    uuids = frozenset(d["uuid_catalogo"] for d in dados)
    return Retorno(dados, medicamentos=uuids, resumo={"n": len(dados), "uuids": sorted(uuids)})


@metodo("medicamento_por_principio",
        "Busca medicamentos do catalogo pelo principio ativo (ou nome alternativo). Devolve uuid_catalogo.", ArgsTermo)
def por_principio(ctx, a: ArgsTermo) -> Retorno:
    return _lista(ctx.medicamentos.buscar_por_principio(a.termo, a.limite))


@metodo("medicamento_por_indicacao",
        "Busca medicamentos cuja indicacao terapeutica combina com o termo (ex.: 'pneumonia').", ArgsTermo)
def por_indicacao(ctx, a: ArgsTermo) -> Retorno:
    return _lista(ctx.medicamentos.buscar_por_indicacao(a.termo, a.limite))


@metodo("medicamento_por_classe",
        "Busca medicamentos por classe farmaceutica (ex.: 'penicilina').", ArgsTermo)
def por_classe(ctx, a: ArgsTermo) -> Retorno:
    return _lista(ctx.medicamentos.buscar_por_classe(a.termo, a.limite))


@metodo("medicamento_detalhe",
        "Detalha um medicamento do catalogo: classe, indicacoes e contraindicacoes.", ArgsUuid)
def detalhe(ctx, a: ArgsUuid) -> Retorno:
    m = ctx.medicamentos.find_by_uuid(a.uuid_catalogo)
    if m is None:
        return Retorno({"erro": "medicamento nao encontrado no catalogo"}, resumo={"n": 0})
    d = compacto_med(m)
    return Retorno(d, medicamentos=frozenset({d["uuid_catalogo"]}), resumo={"n": 1, "uuids": [d["uuid_catalogo"]]})


@metodo("interacoes_com_uso_atual",
        "Interacoes entre um medicamento candidato e os medicamentos que o paciente ja usa.", ArgsUuid)
def interacoes(ctx, a: ArgsUuid) -> Retorno:
    if not ctx.uuids_em_uso:
        return Retorno({"interacoes": [], "observacao": "paciente sem medicamento em uso com catalogo"},
                       resumo={"n": 0})
    itens = [compacto_interacao(i) for i in
             ctx.medicamentos.interacoes_entre(a.uuid_catalogo, sorted(ctx.uuids_em_uso))]
    return Retorno({"interacoes": itens}, resumo={"n": len(itens)})
