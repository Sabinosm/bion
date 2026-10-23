"""
estatisticas_alergia.py

Estatísticas de alergias reportadas: ranking das substâncias mais comuns e
distribuição de gravidade das reações, geral e por substância. O ranking é
apenas informativo. A gravidade traz interpretação em que percentual alto de
reações graves é ruim, sem comparação com período anterior, pois o cadastro é
acumulado e não há filtro de período.
"""

from src.domains.paciente.services.alergia_service import AlergiaService
from src.domains.estatisticas.interpretacao_helper import interpretacao_percentual

_alergia_svc = AlergiaService()


def _percentual_graves(por_gravidade: dict):
    """Percentual de reações 'grave' (uma casa decimal), ou None se não há reações."""
    total = sum(por_gravidade.values())
    if not total:
        return None
    return round((por_gravidade.get("grave", 0) / total) * 100, 1)


class EstatisticasAlergia:

    def top_substancias(self, id_empresa, limite=10):
        """Ranking de substâncias alérgenas mais reportadas (D2).

        Sem interpretação de bom/ruim: qual substância "deveria" ser
        mais reportada não tem lado bom/ruim, é só um ranking informativo.

        Retorna: {"ranking": [{"substancia", "total"}, ...], "leitura": str}
        """
        ranking = _alergia_svc.top_substancias(id_empresa=id_empresa, limite=limite)

        leitura = None
        if ranking:
            principal = ranking[0]
            leitura = (
                f"{principal['substancia']} foi a substância alérgena mais reportada "
                f"({principal['total']} casos)"
            )

        return {"ranking": ranking, "leitura": leitura}

    def gravidade_por_substancia(self, id_empresa, substancia):
        """Percentual de reações graves para uma substância específica (D2,
        drill-down). Sem `comparacao` com período anterior: a rota não
        tem filtro de `dias` e a amostra por substância costuma ser
        pequena, então não há uma janela anterior bem definida.

        Retorna: {"substancia": str, "por_gravidade": {...}, "leitura": str, "interpretacao": {...}}
        """
        por_gravidade = _alergia_svc.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)
        pct_graves = _percentual_graves(por_gravidade)

        if pct_graves is None:
            return {"substancia": substancia, "por_gravidade": por_gravidade, "leitura": None, "interpretacao": None}

        interpretacao = interpretacao_percentual(
            valor=pct_graves,
            texto="Alto = maior risco associado a essa substância; considerar alerta reforçado na triagem e prescrição",
            direcao="alto_ruim",
            comparacao=None,
        )

        return {
            "substancia": substancia,
            "por_gravidade": por_gravidade,
            "leitura": f"{pct_graves}% das reações a {substancia} foram classificadas como graves",
            "interpretacao": interpretacao,
        }

    def gravidade_geral(self, id_empresa):
        """Percentual de reações graves considerando toda a base de
        alergias cadastradas, sem filtro de substância (F4). Sem
        `comparacao`: reflete o cadastro acumulado (sem filtro de
        `dias`), não uma janela temporal comparável a um período anterior.

        Retorna: {"por_gravidade": {...}, "leitura": str, "interpretacao": {...}}
        """
        por_gravidade = _alergia_svc.gravidade_geral(id_empresa=id_empresa)
        pct = _percentual_graves(por_gravidade)

        if pct is None:
            return {"por_gravidade": por_gravidade, "leitura": None, "interpretacao": None}

        interpretacao = interpretacao_percentual(
            valor=pct,
            texto="Alto = base de pacientes com maior propensão a reações graves; reforçar alertas automáticos de prescrição",
            direcao="alto_ruim",
            comparacao=None,
        )

        return {
            "por_gravidade": por_gravidade,
            "leitura": f"{pct}% de todas as reações alérgicas registradas foram classificadas como graves",
            "interpretacao": interpretacao,
        }