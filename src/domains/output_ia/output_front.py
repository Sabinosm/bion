"""output_front: dados formatados para o front exibir.

Junta o que a IA disse (OutputIA) com o que o sistema gravou
(ResultadoPrescricao.to_dict()) e com a qualidade do input (indices).
Nao acessa banco: recebe dicts.
"""
from __future__ import annotations

from .schema import OutputIA


def montar_output_front(output: OutputIA, resultado: dict | None = None, *,
                        indices: dict | None = None, lacunas: list[str] | None = None) -> dict:
    p = output.proposta
    if (p.medicamentos or p.exames) and resultado is None:
        raise ValueError("proposta com itens exige o resultado gravado (ResultadoPrescricao.to_dict()).")

    conduta = None
    if resultado is not None and not p.sem_recomendacao:
        just = {j.uuid_catalogo: j.justificativa for j in output.justificativas_medicamentos}
        meds = []
        for m in resultado.get("medicamentos", []):
            cat = m.get("medicamento") or {}
            meds.append({"uuid": m.get("uuid"), "nome": cat.get("principio_ativo"),
                         "classe": cat.get("classe_farmaceutica"), "dose": m.get("dose"),
                         "frequencia": m.get("frequencia"), "duracao": m.get("duracao"),
                         "orientacoes": m.get("orientacoes"),
                         "justificativa": just.get(cat.get("uuid")),
                         "origem": m.get("origem_sugestao")})
        exs = []
        for e in resultado.get("exames", []):
            ex = e.get("exame") or {}
            exs.append({"uuid": e.get("uuid"), "nome": ex.get("nome_exame"), "tipo": ex.get("tipo"),
                        "urgencia": e.get("urgencia"), "justificativa": e.get("justificativa"),
                        "origem": e.get("origem_sugestao")})
        conduta = {"resultado_uuid": resultado.get("uuid"), "status": resultado.get("status"),
                   "diagnostico": {"cid10": resultado.get("codigo_cid10_principal"),
                                   "descricao": resultado.get("descricao_cid10_principal"),
                                   "certeza": resultado.get("certeza_diagnostica")},
                   "tipo_prescricao": resultado.get("tipo_prescricao"),
                   "medicamentos": meds, "exames": exs}

    ind = indices or {}
    return {"precisa_mais_informacao": output.precisa_mais_informacao,
            "perguntas": [q.model_dump(mode="json") for q in output.perguntas_pendentes],
            "explicacao": output.detalhamento_explicacao,
            "conduta": conduta,
            "qualidade": {"completude": ind.get("completude"), "confianca": ind.get("confianca"),
                          "motivos": ind.get("motivos_confianca", [])},
            "lacunas": list(lacunas or []),
            "blocos_considerados": list(output.blocos_considerados)}
