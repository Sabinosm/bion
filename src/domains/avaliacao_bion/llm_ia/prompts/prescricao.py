"""prescricao.py

Monta a conversa inicial com a IA a partir do template versionado de prescrição (templates/prescricao_bion/<versao>.md) e traz a mensagem de correção enviada quando a resposta é rejeitada.

O texto das instruções vive no template, não no código. Mudou o texto? Crie uma versão nova do template e suba VERSAO_PROMPT: ela vai junto da versão do modelo em OutputBion.versao_modelo_ia. Todo prompt carrega o aviso de projeto acadêmico com dados fictícios.
"""
from __future__ import annotations

import json
from .prompt_service import PromptService

VERSAO_PROMPT = 2
TIPO_PROMPT = "prescricao_bion"

_servico = PromptService()


def conversa_inicial(prompt_input: str) -> list[dict]:
    prompt = _servico.montar(TIPO_PROMPT, f"v{VERSAO_PROMPT}", prompt_input)
    return [{"papel": "sistema", "conteudo": prompt.sistema},
            {"papel": "usuario", "conteudo": prompt.usuario}]


def feedback_rejeicao(erros: list[str], pode_usar_ferramentas: bool) -> dict:
    corpo = "\n".join(f"- {e}" for e in erros)
    extra = "" if pode_usar_ferramentas else "\nNao ha mais rodadas de consulta: responda agora com os dados que voce tem."
    return {"papel": "usuario",
            "conteudo": f"Sua resposta foi rejeitada. Corrija e responda de novo, so com o JSON:\n{corpo}{extra}"}


def texto(resposta) -> str:
    return resposta if isinstance(resposta, str) else json.dumps(resposta, ensure_ascii=False)
