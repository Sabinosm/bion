"""
Motor de IA generativa via API do Claude (Anthropic), usado como suporte
adicional à decisão clínica além dos protocolos determinísticos
(MTS/NEWS2). A decisão final é sempre do profissional de saúde — o
prompt reforça isso explicitamente e o resultado nunca é persistido como
diagnóstico definitivo sem revisão humana.
"""

import os
import json
import requests

from .ia_base import IMotorIA, ContextoClinico


class LlmMotor(IMotorIA):
    """Implementação de IMotorIA que consulta a API de mensagens da Anthropic."""

    def __init__(self):
        """Lê as configurações de API (chave, modelo, URL) das variáveis de ambiente."""
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.modelo = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
        self.url_base = os.getenv("LLM_URL", "https://api.anthropic.com/v1/messages")

    def analisar(self, ctx: ContextoClinico) -> dict:
        """
        Monta o prompt a partir do contexto clínico, chama a API do
        modelo e faz o parse da resposta em JSON.

        Returns:
            dict com diagnosticos, medicamentos_sugeridos, exames_sugeridos
            e alertas. Em caso de resposta não-parseável, retorna um dict
            vazio com um alerta de erro de interpretação.
        """
        prompt = (
            "Você é um sistema de apoio à decisão clínica. "
            "Analise os dados abaixo e responda SOMENTE em JSON com a estrutura: "
            "{diagnosticos, medicamentos_sugeridos, exames_sugeridos, alertas}. "
            "A decisão final é sempre do profissional de saúde.\n\n"
            f"Dados: {json.dumps(ctx.serializar(), ensure_ascii=False)}"
        )
        resp = requests.post(
            self.url_base,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.modelo,
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"]
        try:
            limpo = raw.strip()
            if limpo.startswith("```"):
                limpo = limpo.strip("`")
                if limpo.startswith("json"):
                    limpo = limpo[4:]
            return json.loads(limpo.strip())
        except (json.JSONDecodeError, KeyError, IndexError):
            return {
                "diagnosticos": [],
                "medicamentos_sugeridos": [],
                "exames_sugeridos": [],
                "alertas": ["Erro ao interpretar a resposta do modelo de IA."],
            }

    def get_nome_modelo(self):
        """Retorna o identificador do modelo de IA utilizado."""
        return self.modelo

    def get_versao(self):
        """Retorna a versão do motor de IA."""
        return "1.0"
