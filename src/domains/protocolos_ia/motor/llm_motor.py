"""
Motor de IA generativa via API do Claude (Anthropic), usado como suporte
adicional a decisao clinica alem dos protocolos deterministicos
(MTS/NEWS2). A decisao final e sempre do profissional de saude -- o
prompt reforca isso explicitamente e o resultado nunca e persistido como
diagnostico definitivo sem revisao humana.
"""

import os
import json
import requests

from .ia_base import IMotorIA, ContextoClinico


class LlmMotor(IMotorIA):
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.modelo = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
        self.url_base = os.getenv("LLM_URL", "https://api.anthropic.com/v1/messages")

    def analisar(self, ctx: ContextoClinico) -> dict:
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
        return self.modelo

    def get_versao(self):
        return "1.0"
