"""output_front.py

output_front: dados formatados para o front exibir.

Junta o que a IA disse (OutputIA) com o que o sistema gravou
(ResultadoPrescricao.to_dict()) e com a qualidade do input (indices).
Nao acessa banco: recebe dicts. `substituida=True`: o rascunho desta avaliacao foi
trocado por uma avaliacao mais nova; a conduta nao e mostrada, so a explicacao.
"""
from __future__ import annotations

from .schema import OutputIA


# Texto exibivel de cada sinal de baixa confianca (codigos em input_ia.nucleo.Sinal).
_DESCRICAO_MOTIVO = {
    "dados_clinicos_divergem": "O que foi marcado e o que foi registrado se contradizem",
    "conferencia_pendente": "Há registros, mas a informação não foi conferida neste atendimento",
    "alergia_nao_confirmada": "Alergia registrada sem confirmação",
    "medicamento_sem_catalogo": "Medicamento fora do catálogo: interações não verificadas",
    "sinal_vital_fora_do_limite": "Sinal vital fora da faixa esperada",
    "protocolo_incompleto": "Protocolo executado com dados incompletos",
    "dado_critico_ausente": "Dado crítico do protocolo ausente",
}


def _motivo_legivel(m: dict) -> dict:
    """Acrescenta `descricao` (texto pronto para a tela) ao motivo, sem remover os campos originais."""
    texto = _DESCRICAO_MOTIVO.get(m.get("codigo"), str(m.get("codigo") or "motivo não identificado"))
    n = m.get("ocorrencias") or 1
    sufixo = f" ({n} ocorrências)" if n > 1 else ""
    return {**m, "descricao": f"{m.get('bloco', '')}: {texto}{sufixo}".lstrip(": ")}


def montar_output_front(output: OutputIA, resultado: dict | None = None, *,
                        indices: dict | None = None, lacunas: list[str] | None = None,
                        substituida: bool = False) -> dict:
    """Dict final para o front. Levanta ValueError se a proposta tem itens e o resultado gravado nao foi informado
    (exceto quando `substituida`)."""
    p = output.proposta
    if (p.medicamentos or p.exames) and resultado is None and not substituida:
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
    return {"conduta_substituida": bool(substituida and resultado is None),
            "precisa_mais_informacao": output.precisa_mais_informacao,
            "perguntas": [q.model_dump(mode="json") for q in output.perguntas_pendentes],
            "explicacao": output.detalhamento_explicacao,
            "conduta": conduta,
            "qualidade": {"completude": ind.get("completude"), "confianca": ind.get("confianca"),
                          "motivos": [_motivo_legivel(m) for m in ind.get("motivos_confianca", [])]},
            "lacunas": list(lacunas or []),
            "blocos_considerados": list(output.blocos_considerados)}