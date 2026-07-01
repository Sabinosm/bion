"""
Protocolo NEWS2 (National Early Warning Score 2, RCP 2017).

Ver nota de correcoes em `base.py`: `inp.sinais_vitais` e os campos de
`ResultadoTriagem` usados aqui (`nivel_risco_news2`, `score_news2`,
`subscores_news2`) so existem porque `base.py` foi ajustado para
comporta-los. A logica de calculo do score (faixas de pontuacao,
threshold de nivel de risco) foi mantida identica ao codigo original.
"""

from .base import (
    IProtocoloTriagem, IProtocoloConsulta,
    InputTriagem, InputConsulta, ResultadoTriagem, ResultadoConsulta,
)

FAIXAS = {
    "frequencia-respiratoria": [(0, 8, 3), (9, 11, 1), (12, 20, 0), (21, 24, 2), (25, 999, 3)],
    "spo2": [(0, 91, 3), (92, 93, 2), (94, 95, 1), (96, 100, 0)],
    "pa-sistolica": [(0, 90, 3), (91, 100, 2), (101, 110, 1), (111, 219, 0), (220, 999, 3)],
    "frequencia-cardiaca": [(0, 40, 3), (41, 50, 1), (51, 90, 0), (91, 110, 1), (111, 130, 2), (131, 999, 3)],
    "temperatura": [(0, 35.0, 3), (35.1, 36.0, 1), (36.1, 38.0, 0), (38.1, 39.0, 1), (39.1, 99, 2)],
}


class News2Protocolo(IProtocoloTriagem, IProtocoloConsulta):
    VERSAO = "NEWS2-2017"

    def _calcular(self, sinais):
        mapa = {s["tipo_parametro"]: float(s["valor_numerico"]) for s in sinais}
        sub = {}
        for p, faixas in FAIXAS.items():
            if p in mapa:
                for lo, hi, pts in faixas:
                    if lo <= mapa[p] <= hi:
                        sub[p] = pts
                        break
        avpu = mapa.get("avpu_valor", 0)
        sub["consciencia"] = 0 if avpu == 0 else 3
        total = sum(sub.values())
        escalado = next((p for p, v in sub.items() if v >= 3), None)
        nivel = "alto" if total >= 7 or escalado else "medio" if total >= 5 else "baixo"
        return sub, total, nivel, escalado

    def executar(self, inp):
        sub, total, nivel, escalado = self._calcular(inp.sinais_vitais)
        alertas = [f"Parâmetro crítico: {escalado}"] if escalado else []
        if isinstance(inp, InputTriagem):
            return ResultadoTriagem(
                nivel_risco_news2=nivel,
                score_news2=total,
                subscores_news2=sub,
                alertas=alertas,
            )
        return ResultadoConsulta(indice_confianca=0.7, alertas=alertas)

    def validar_input(self, i) -> bool:
        return len(i.sinais_vitais) > 0

    def get_nome(self):
        return "NEWS2"

    def get_versao(self):
        return self.VERSAO
