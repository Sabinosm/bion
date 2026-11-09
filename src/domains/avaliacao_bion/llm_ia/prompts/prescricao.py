"""prescricao.py

Monta a conversa inicial com a IA a partir do template versionado de prescrição (templates/prescricao_bion/<versao>.md) e traz a mensagem de correção enviada quando a resposta é rejeitada.

O texto das instruções vive no template, não no código. Mudou o texto? Crie uma versão nova do template e suba VERSAO_PROMPT: ela vai junto da versão do modelo em OutputBion.versao_modelo_ia. Todo prompt carrega o aviso de projeto acadêmico com dados fictícios.

O JSON Schema da resposta é anexado às regras do sistema em código (não no template), para que a IA o veja
mesmo quando o provedor não impõe o esquema na chamada (ex.: Gemini com ferramentas fora de modelos 3+).
"""
from __future__ import annotations

import json
from .prompt_service import PromptService

VERSAO_PROMPT = 3
TIPO_PROMPT = "prescricao_bion"

_servico = PromptService()


def _bloco_esquema(esquema: dict) -> str:
    # esquema cru (com pattern, format, minLength...): em texto essas restrições ajudam o modelo
    texto_esquema = json.dumps(esquema, ensure_ascii=False, indent=1)
    return ("\n\nFORMATO OBRIGATÓRIO DA RESPOSTA FINAL (JSON Schema). "
            "Devolva um único objeto JSON que obedeça a este esquema, sem campos extras:\n" + texto_esquema)


def conversa_inicial(prompt_input: str, esquema: dict | None = None) -> list[dict]:
    prompt = _servico.montar(TIPO_PROMPT, f"v{VERSAO_PROMPT}", prompt_input)
    sistema = prompt.sistema + (_bloco_esquema(esquema) if esquema else "")
    return [{"papel": "sistema", "conteudo": sistema},
            {"papel": "usuario", "conteudo": prompt.usuario}]


def feedback_rejeicao(erros: list[str], pode_usar_ferramentas: bool) -> dict:
    corpo = "\n".join(f"- {e}" for e in erros)
    extra = "" if pode_usar_ferramentas else "\nNao ha mais rodadas de consulta: responda agora com os dados que voce tem."
    return {"papel": "usuario",
            "conteudo": ("Sua resposta foi rejeitada. Corrija TODOS os erros abaixo e responda de novo "
                         f"com o objeto JSON completo, so o JSON:\n{corpo}{extra}")}


def texto(resposta) -> str:
    return resposta if isinstance(resposta, str) else json.dumps(resposta, ensure_ascii=False)
