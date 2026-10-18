"""Apoio compartilhado do grupo 'atendimento' (nao e um bloco: o '_' impede o registro)."""
from __future__ import annotations

from ..nucleo import iso, limpar, num

SINAIS_ESPERADOS = ("frequencia-respiratoria", "spo2", "pa-sistolica", "pa-diastolica",
                    "frequencia-cardiaca", "temperatura", "glicemia-capilar")


def ultimos_sinais(atendimento) -> dict:
    """Ultima medicao valida de cada tipo dentro do atendimento."""
    validos = [s for s in atendimento.sinais_vitais
               if s.flag_validacao_faixa != "fora-limite-rejeitado"]
    validos.sort(key=lambda s: (s.data_hora_medicao, s.id))
    ultimo = {s.tipo_parametro: s for s in validos}  # o mais recente sobrescreve
    return {
        tipo: limpar({
            "valor": num(s.valor_numerico),
            "unidade": s.unidade,
            "sitio_medicao": s.sitio_medicao,
            "medido_em": iso(s.data_hora_medicao),
            "alerta": "fora_do_limite" if s.flag_validacao_faixa == "fora-limite-alertado" else None,
            "escala_dpoc": True if s.flag_escala_dpoc else None,
        })
        for tipo, s in ultimo.items()
    }


def coletas(atendimento) -> list[dict]:
    """So a coleta VIGENTE (a de maior id): a coleta e insert-only, o medico
    pode refaze-la e a ultima e a que vale. As anteriores nao vao para a IA."""
    cs = sorted(atendimento.coletas_clinicas, key=lambda c: c.id)[-1:]
    return [limpar({"desde_quando_sintomas_horas": c.desde_quando_sintomas}) for c in cs]


def condutas(atendimento) -> list[dict]:
    cs = sorted(atendimento.condutas_enfermagem, key=lambda c: (c.criado_em, c.id))
    return [limpar({
        "descricao": c.descricao_conduta,
        "registrada_em": iso(c.criado_em),
        "protocolo": c.protocolo_catalogo.nome_protocolo if c.protocolo_catalogo else None,
    }) for c in cs]


def anteriores(at) -> list:
    """Atendimentos da mesma consulta que vieram antes deste (sem cancelados)."""
    chave = (at.data_hora_inicio, at.id)
    return sorted(
        (a for a in at.consulta.atendimentos
         if a.id != at.id and a.status != "cancelado"
         and (a.data_hora_inicio, a.id) < chave),
        key=lambda a: (a.data_hora_inicio, a.id),
    )
