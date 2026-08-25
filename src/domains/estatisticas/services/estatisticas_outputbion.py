from src.domains.protocolos_ia.service import OutputBionService

ob_svc = OutputBionService()


class EstatisticasOutputBion:
 
    # --- B1: Confiança média da IA ---
    def confianca_media(self, id_empresa, dias=30):
        """Retorna: {"media": float|None, "dias": int, "leitura": str}"""
        media = ob_svc.media_confianca(id_empresa=id_empresa, dias=dias)
        leitura = (
            f"Confiança média da IA nos últimos {dias} dias: {round(media, 1)}%"
            if media is not None else "Sem execuções da IA no período"
        )
        return {"media": round(media, 2) if media is not None else None, "dias": dias, "leitura": leitura}
 
    # --- B2: Completude média dos dados de entrada ---
    def completude_media(self, id_empresa, dias=30):
        """Retorna: {"media": float|None, "dias": int, "leitura": str}"""
        media = ob_svc.media_completude(id_empresa=id_empresa, dias=dias)
        leitura = (
            f"Completude média dos dados de entrada: {round(media, 1)}%"
            if media is not None else "Sem execuções da IA no período"
        )
        return {"media": round(media, 2) if media is not None else None, "dias": dias, "leitura": leitura}
 
    # --- B4: Versão do modelo de IA em uso ---
    def versoes_em_uso(self, id_empresa, dias=30):
        """Retorna: {"versoes": [...], "leitura": str}"""
        versoes = ob_svc.versoes_em_uso(id_empresa=id_empresa, dias=dias)
 
        leitura = None
        if versoes:
            principal = versoes[0]
            if len(versoes) == 1:
                leitura = f"Todas as execuções usaram o modelo {principal['versao_modelo_ia']}"
            else:
                leitura = (
                    f"{len(versoes)} versões de modelo em uso no período -- "
                    f"predominante: {principal['versao_modelo_ia']} ({principal['total']} execuções)"
                )
 
        return {"versoes": versoes, "leitura": leitura}
 
    # --- E3: Correlação completude x confiança ---
    def correlacao_completude_confianca(self, id_empresa, dias=30):
        """Coeficiente de correlação de Pearson entre indice_completude
        e indice_confianca dos outputs no período -- indica se dados de
        entrada mais completos tendem a gerar respostas com mais
        confiança da IA.
 
        Implementado sem numpy/scipy (dependência extra) -- Pearson na
        mão, com os pares (completude, confianca) do período.
 
        Retorna: {"coeficiente": float|None, "n_amostras": int, "leitura": str}
        """
        pares = ob_svc.pares_completude_confianca(id_empresa=id_empresa, dias=dias)
 
        n = len(pares)
        if n < 2:
            return {"coeficiente": None, "n_amostras": n, "leitura": "Amostra insuficiente para calcular correlação"}
 
        xs = [p[0] for p in pares]
        ys = [p[1] for p in pares]
        media_x = sum(xs) / n
        media_y = sum(ys) / n
 
        cov = sum((x - media_x) * (y - media_y) for x, y in pares)
        var_x = sum((x - media_x) ** 2 for x in xs)
        var_y = sum((y - media_y) ** 2 for y in ys)
 
        if var_x == 0 or var_y == 0:
            return {"coeficiente": None, "n_amostras": n, "leitura": "Sem variação suficiente nos dados para calcular correlação"}
 
        coeficiente = round(cov / (var_x ** 0.5 * var_y ** 0.5), 3)
 
        if coeficiente >= 0.7:
            forca = "forte"
        elif coeficiente >= 0.4:
            forca = "moderada"
        elif coeficiente >= 0.1:
            forca = "fraca"
        else:
            forca = "praticamente nula"
 
        leitura = f"Correlação {forca} entre completude e confiança (r={coeficiente}, n={n})"
 
        return {"coeficiente": coeficiente, "n_amostras": n, "leitura": leitura}