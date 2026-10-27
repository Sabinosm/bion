"""Apoio ao log de acesso das rotas de prescrição (decorator acesso_auditado).

A prescrição NÃO usa step-up (decisão: não interromper o médico durante o atendimento). Por isso
usa @acesso_auditado (log de acesso: quem, quando, qual recurso, qual operação, de qual paciente),
e não @acao_sensivel, que sempre exige reconfirmação de identidade.

Contrato do decorator (acaoSensivel.py): a view devolve (resposta, detalhes).
  - sucesso: detalhes com uuid_paciente (opcional) -> grava o log DEPOIS da resposta;
  - erro ou nada alterado: detalhes {"operacao": "NOOP"} -> NÃO grava nada. O decorator não olha o
    status HTTP: sem o NOOP, um 403/404/409 seria registrado como acesso com sucesso.
"""

NOOP = {"operacao": "NOOP"}


def detalhes(resultado) -> dict:
    """Detalhes do log de um resultado de prescrição: só o uuid do paciente (nunca dado clínico)."""
    try:
        return {"uuid_paciente": resultado.atendimento.consulta.paciente.uuid}
    except AttributeError:
        return {}


def erro(resposta):
    """Resposta de erro + sinal para o decorator não registrar nada."""
    return resposta, NOOP