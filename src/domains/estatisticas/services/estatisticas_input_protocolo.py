import re
from collections import Counter


from src.domains.protocolos_ia.service import OutputBionService

obs = OutputBionService()

# stopwords mínimas de português pra não poluir o ranking com preposições
_STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "no", "na",
    "com", "sem", "por", "para", "que", "há", "ha", "desde", "um", "uma", "há",
}


def _tokenizar(texto: str) -> list:
    palavras = re.findall(r"[a-zà-ú]+", texto.lower())
    return [p for p in palavras if p not in _STOPWORDS and len(p) > 2]


class EstatisticasInputProtocolo:

    # --- C5: Queixas principais mais frequentes ---
    def queixas_mais_frequentes(self, id_empresa, dias=30, top=15):
        """Ranking aproximado de termos mais citados em queixa_principal.

        Importante: isso é frequência de PALAVRAS, não de frases exatas
        -- texto livre não tem padronização, então "dor de cabeça" e
        "cefaleia" contam como termos diferentes. Serve como direção
        geral, não como estatística médica precisa. Se no futuro
        quiserem algo mais preciso, o caminho é a equipe clínica adotar
        um campo estruturado (dropdown de queixas padronizadas) em vez
        de texto livre -- fora do escopo desta função.

        Retorna: {"termos": [{"termo", "total"}, ...], "total_queixas_analisadas": int, "leitura": str}
        """
        queixas = obs.queixas_recentes(id_empresa=id_empresa, dias=dias)

        contador = Counter()
        for queixa in queixas:
            contador.update(set(_tokenizar(queixa)))  # set() evita contar 2x a mesma palavra na mesma queixa

        termos = [{"termo": termo, "total": total} for termo, total in contador.most_common(top)]

        leitura = None
        if termos:
            leitura = (
                f"Termo mais citado em queixas principais: '{termos[0]['termo']}' "
                f"({termos[0]['total']} de {len(queixas)} queixas)"
            )

        return {"termos": termos, "total_queixas_analisadas": len(queixas), "leitura": leitura}