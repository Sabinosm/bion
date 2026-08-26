from src.domains.estatisticas.interpretacao_helper import interpretacao_sem_nivel
from src.domains.prescricao.prescricao_exame_service import PrescricaoExameService

pes = PrescricaoExameService()


class EstatisticasPrescricaoExame:
 
    # --- D3: Urgência de exames -- IA vs. profissional ---
    def urgencia_por_origem(self, id_empresa, dias=30):
        """Cruzamento urgencia x origem_sugestao, com % de participação
        da IA em cada nível de urgência.
 
        Grupo 2 -- sem nivel/comparacao: é uma matriz cruzada (urgência
        x origem), não um valor único -- comparar a matriz inteira com
        o período anterior polui mais do que ajuda. direcao neutro:
        maior % de sugestão pela IA não é bom nem ruim por si só.
 
        Retorna: {"matriz": [...], "leitura": str, "interpretacao": {...}}
        """
        bruto = pes.urgencia_por_origem(id_empresa=id_empresa, dias=dias)
 
        total_por_urgencia = {}
        for item in bruto:
            total_por_urgencia[item["urgencia"]] = total_por_urgencia.get(item["urgencia"], 0) + item["total"]
 
        matriz = [
            {
                **item,
                "percentual": round((item["total"] / total_por_urgencia[item["urgencia"]]) * 100, 1)
                if total_por_urgencia[item["urgencia"]] else 0.0,
            }
            for item in bruto
        ]
 
        urgentes = [item for item in matriz if item["urgencia"] == "urgente"]
        leitura = None
        if urgentes:
            partes = [f"{item['percentual']}% pela {item['origem_sugestao']}" for item in urgentes]
            leitura = f"Exames marcados como urgentes: {', '.join(partes)}"
 
        interpretacao = interpretacao_sem_nivel(
            texto="Grande divergência entre IA e profissional na classificação de urgência pode indicar necessidade de calibrar o modelo ou revisar critérios da equipe -- não há um 'lado certo' fixo aqui",
            direcao="neutro",
            comparacao=None,
        )
 
        return {"matriz": matriz, "leitura": leitura, "interpretacao": interpretacao}