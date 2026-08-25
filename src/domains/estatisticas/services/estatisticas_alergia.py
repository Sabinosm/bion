from src.domains.paciente.services import DadosClinicosService
from ..interpretacao_helper import interpretacao_percentual

dcs = DadosClinicosService()

class EstatisticasAlergia:
 
    # --- D2: Alergias mais reportadas ---
    def top_substancias(self, id_empresa, limite=10):
        """Grupo 3 -- ranking de contagem, sem interpretação (qual
        substância "deveria" ser mais reportada não tem lado bom/ruim).
 
        Retorna: {"ranking": [{"substancia", "total"}, ...], "leitura": str}
        """
        ranking = dcs.top_substancias(id_empresa=id_empresa, limite=limite)
 
        leitura = None
        if ranking:
            principal = ranking[0]
            leitura = (
                f"{principal['substancia']} foi a substância alérgena mais reportada "
                f"({principal['total']} casos)"
            )
 
        return {"ranking": ranking, "leitura": leitura}
 
    # --- D2 (detalhe): drill-down de gravidade por substância ---
    def gravidade_por_substancia(self, id_empresa, substancia):
        """Grupo 1 -- % com threshold, direcao alto_ruim (mais % grave
        é pior). comparacao fica None aqui: esta rota não tem filtro de
        `dias`, então não existe "período anterior" bem definido para
        1 substância específica com amostra normalmente pequena.
 
        Retorna: {"substancia": str, "por_gravidade": {...}, "leitura": str, "interpretacao": {...}}
        """
        por_gravidade = dcs.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)
        total = sum(por_gravidade.values())
        graves = por_gravidade.get("grave", 0)
 
        if not total:
            return {"substancia": substancia, "por_gravidade": por_gravidade, "leitura": None, "interpretacao": None}
 
        pct_graves = round((graves / total) * 100, 1)
 
        interpretacao = interpretacao_percentual(
            valor=pct_graves,
            texto="Alto = maior risco associado a essa substância; considerar alerta reforçado na triagem e prescrição",
            direcao="alto_ruim",
            comparacao=None,  # sem janela de dias nesta rota, não há período anterior a comparar
        )
 
        return {
            "substancia": substancia,
            "por_gravidade": por_gravidade,
            "leitura": f"{pct_graves}% das reações a {substancia} foram classificadas como graves",
            "interpretacao": interpretacao,
        }
 
    # --- F4: Gravidade geral das reações alérgicas (sem filtro por substância) ---
    def gravidade_geral(self, id_empresa):
        """Grupo 1 -- % com threshold, direcao alto_ruim. comparacao
        também None: rota reflete o cadastro acumulado (sem `dias`),
        não uma janela temporal comparável a um "período anterior".
 
        Retorna: {"por_gravidade": {...}, "leitura": str, "interpretacao": {...}}
        """
        por_gravidade = dcs.gravidade_geral(id_empresa=id_empresa)
        total = sum(por_gravidade.values())
        graves = por_gravidade.get("grave", 0)
 
        if not total:
            return {"por_gravidade": por_gravidade, "leitura": None, "interpretacao": None}
 
        pct = round((graves / total) * 100, 1)
 
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