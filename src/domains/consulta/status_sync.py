"""
Única fonte de verdade para Consulta.status_consulta.

status_consulta é um campo DERIVADO do conjunto de Atendimentos da
Consulta. Nunca deve ser setado manualmente fora daqui -- todo
método de AtendimentoService que cria, finaliza ou cancela um
Atendimento deve terminar chamando sincronizar_status_consulta.

Exceção: "encerrada" é um estado terminal setado explicitamente por
ConsultaService.encerrar (ação humana explícita, não derivável do
histórico de Atendimentos). Uma vez "encerrada", esta função não
sobrescreve mais o status.
"""


def sincronizar_status_consulta(consulta, atendimentos_ordenados):
    """
    Recalcula consulta.status_consulta a partir dos Atendimentos.

    Args:
        consulta: instância de Consulta (mutada in-place, não commitada
                  aqui -- quem chama decide a transação).
        atendimentos_ordenados: List[Atendimento] da consulta, em ordem
                  cronológica crescente (mais antigo primeiro). Passar
                  o resultado de AtendimentoRepository.find_por_consulta.
    """
    if consulta.status_consulta == "encerrada":
        return  # estado terminal -- só ConsultaService.encerrar mexe aqui

    if not atendimentos_ordenados:
        consulta.status_consulta = "aguardando-triagem"
        return

    ultimo = atendimentos_ordenados[-1]

    if ultimo.status == "em-andamento":
        consulta.status_consulta = {
            "triagem": "em-triagem",
            "avaliacao-medica": "em-atendimento",
            "reavaliacao": "em-atendimento",
            "procedimento": "em-observacao",
            "alta": "em-atendimento",
        }.get(ultimo.tipo_atendimento, "em-atendimento")
        return

    # último Atendimento não está em-andamento (finalizado/cancelado):
    # o status depende do que já foi feito, não só do último registro.
    tipos_finalizados = {
        a.tipo_atendimento for a in atendimentos_ordenados
        if a.status == "finalizado"
    }

    if "triagem" in tipos_finalizados and not (
        "avaliacao-medica" in tipos_finalizados or "reavaliacao" in tipos_finalizados
    ):
        consulta.status_consulta = "aguardando-medico"
    elif "avaliacao-medica" in tipos_finalizados or "reavaliacao" in tipos_finalizados:
        consulta.status_consulta = "em-observacao"
    else:
        # só houve atendimentos cancelados, ou nenhum finalizado ainda
        consulta.status_consulta = "aguardando-triagem"