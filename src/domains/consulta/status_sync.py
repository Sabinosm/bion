"""
Única fonte de verdade para Consulta.status_consulta.

status_consulta é um campo DERIVADO do conjunto de Atendimentos da
Consulta. Nunca deve ser setado manualmente fora daqui -- todo
método de AtendimentoService que cria, finaliza ou cancela um
Atendimento deve terminar chamando sincronizar_status_consulta.

Exceção: "encerrada" é um estado terminal setado explicitamente por
ConsultaService.encerrar / evadir (ação humana explícita, não derivável
do histórico de Atendimentos). Uma vez "encerrada", esta função não
sobrescreve mais o status.

MODELO: a Consulta é o episódio de um problema de saúde e os Atendimentos
são etapas dentro dela (1:N). Não há ordem obrigatória nem correlação
entre triagem e avaliação médica -- pode haver triagem sem avaliação,
avaliação sem triagem, e qualquer tipo pode se repetir (inclusive num
retorno pelo mesmo problema). Por isso o status NÃO depende de "quais
tipos já foram feitos", e sim do que aconteceu por último.
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
        return  # estado terminal -- só ConsultaService.encerrar/evadir mexe aqui

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

    # Nenhum em andamento (o último está finalizado ou cancelado): o status
    # depende do ÚLTIMO Atendimento FINALIZADO, não do conjunto de tipos.
    # Assim, uma nova triagem de retorno depois de uma avaliação volta a
    # "aguardando-medico" em vez de ficar presa em "em-observacao".
    finalizados = [a for a in atendimentos_ordenados if a.status == "finalizado"]

    if not finalizados:
        # só houve atendimentos cancelados: nada foi concluído ainda
        consulta.status_consulta = "aguardando-triagem"
    elif finalizados[-1].tipo_atendimento == "triagem":
        consulta.status_consulta = "aguardando-medico"
    else:
        consulta.status_consulta = "em-observacao"