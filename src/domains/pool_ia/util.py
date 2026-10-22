from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

Termo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Limite = Annotated[int, Field(ge=1, le=20)]


def compacto_med(m) -> dict:
    d = m.to_dict()
    return {"uuid_catalogo": d["uuid"], "principio_ativo": d.get("principio_ativo"),
            "classe_farmaceutica": d.get("classe_farmaceutica"),
            "indicacoes_terapeuticas": d.get("indicacoes_terapeuticas") or [],
            "contraindicacoes": d.get("contraindicacoes") or []}


def compacto_interacao(i) -> dict:
    """Projecao de InteracoesMedicamentos (uuid, gravidade e os dois medicamentos)."""
    a, b = i.medicamento_a, i.medicamento_b
    d = {"medicamento_a": {"uuid_catalogo": a.uuid, "principio_ativo": a.principio_ativo},
         "medicamento_b": {"uuid_catalogo": b.uuid, "principio_ativo": b.principio_ativo},
         "gravidade": i.gravidade, "descricao": getattr(i, "descricao", None)}
    return {k: v for k, v in d.items() if v is not None}


def compacto_exame(e) -> dict:
    d = e.to_dict()
    return {k: v for k, v in {"uuid_exame": d["uuid"], "nome_exame": d.get("nome_exame"),
                              "nome_exame_en": d.get("nome_exame_en"), "tipo": d.get("tipo"),
                              "material": d.get("material"), "jejum_horas": d.get("jejum_horas"),
                              "codigo_loinc": d.get("codigo_loinc")}.items() if v is not None}
