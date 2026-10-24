"""continuar_service.py -- regras de "o que o profissional pode fazer agora" numa Consulta ou num Atendimento.

Decide, a partir de dados já carregados, se o botão "Continuar" aparece e para onde ele leva
(retomar o atendimento em andamento, registrar o consentimento ou abrir a próxima etapa).
Lógica pura: não acessa o banco nem a sessão; quem chama entrega consulta, atendimento em
andamento, usuário, função clínica e a situação do consentimento. É também o lugar das
constantes que definem quem pode abrir qual etapa.
"""

FUNCOES_CLINICAS = ("enfermeiro", "medico")
STATUS_PARA_REAVALIACAO = ("em-observacao",)

ACAO_CONTINUAR = "continuar-atendimento"
ACAO_CONSENTIMENTO = "registrar-consentimento"
ACAO_DISPENSAR = "dispensar-consentimento"
ACAO_TRIAGEM = "abrir-triagem"
ACAO_AVALIACAO = "abrir-avaliacao-medica"
ACAO_REAVALIACAO = "abrir-reavaliacao"

# Etapa sugerida por status_consulta (a de maior prioridade para aquele momento).
_ACAO_PRINCIPAL = {
    "aguardando-triagem": ACAO_TRIAGEM,
    "aguardando-medico": ACAO_AVALIACAO,
    "em-observacao": ACAO_REAVALIACAO,
}


def avaliar_continuidade(consulta, atendimento_em_andamento, id_usuario, funcao,
                         consentimento_pendente: bool = False) -> dict:
    """Continuidade de uma Consulta para o profissional logado.

    Devolve: pode_continuar (bool), proxima_acao (a ação sugerida, ou None), acoes_disponiveis
    (todas as ações permitidas agora), atendimento_em_andamento ({uuid, tipo_atendimento, meu} ou
    None) e motivo_bloqueio (por que não pode continuar, ou None). Ordem de decisão: Consulta
    encerrada, função sem permissão clínica, atendimento em andamento (meu ou de outro),
    consentimento pendente e, por fim, abertura da próxima etapa conforme o status e a função.
    """
    r = {
        "pode_continuar": False,
        "proxima_acao": None,
        "acoes_disponiveis": [],
        "atendimento_em_andamento": None,
        "motivo_bloqueio": None,
    }
    if consulta.status_consulta == "encerrada":
        r["motivo_bloqueio"] = "consulta-encerrada"
        return r
    if funcao not in FUNCOES_CLINICAS:
        r["motivo_bloqueio"] = "sem-permissao"
        return r

    a = atendimento_em_andamento
    if a is not None:
        meu = a.realizado_por == id_usuario
        r["atendimento_em_andamento"] = {
            "uuid": a.uuid, "tipo_atendimento": a.tipo_atendimento, "meu": meu,
        }
        if meu:
            r.update(pode_continuar=True, proxima_acao=ACAO_CONTINUAR)
        else:
            r["motivo_bloqueio"] = "atendimento-de-outro-profissional"
        return r

    if consentimento_pendente:
        r.update(pode_continuar=True, proxima_acao=ACAO_CONSENTIMENTO,
                 acoes_disponiveis=[ACAO_CONSENTIMENTO, ACAO_DISPENSAR])
        return r

    disponiveis = [ACAO_TRIAGEM]
    if funcao == "medico":
        disponiveis.append(ACAO_AVALIACAO)
        if consulta.status_consulta in STATUS_PARA_REAVALIACAO:
            disponiveis.append(ACAO_REAVALIACAO)
    r["acoes_disponiveis"] = disponiveis

    principal = _ACAO_PRINCIPAL.get(consulta.status_consulta, ACAO_TRIAGEM)
    if principal in disponiveis:
        r.update(pode_continuar=True, proxima_acao=principal)
    else:
        r["motivo_bloqueio"] = "proxima-etapa-exige-medico"
    return r


def continuidade_atendimento(atendimento, id_usuario) -> dict:
    """Continuidade de um Atendimento: só o dono retoma um atendimento em andamento.

    Devolve pode_continuar, proxima_acao (ACAO_CONTINUAR ou None) e motivo_bloqueio
    ('atendimento-finalizado', 'atendimento-cancelado' ou 'atendimento-de-outro-profissional').
    """
    r = {"pode_continuar": False, "proxima_acao": None, "motivo_bloqueio": None}
    if atendimento.status != "em-andamento":
        r["motivo_bloqueio"] = f"atendimento-{atendimento.status}"
    elif atendimento.realizado_por != id_usuario:
        r["motivo_bloqueio"] = "atendimento-de-outro-profissional"
    else:
        r.update(pode_continuar=True, proxima_acao=ACAO_CONTINUAR)
    return r