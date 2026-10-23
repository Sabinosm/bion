"""
estatisticas_input_protocolo.py

Estatísticas sobre o texto livre digitado nos protocolos: ranking aproximado
dos termos mais citados como queixa principal. A contagem é por palavra, não
por frase, e ignora preposições e palavras muito curtas, então serve como
direção geral e não como estatística médica precisa.
"""

import re
from collections import Counter

from src.domains.avaliacao_bion.service import OutputBionService

_output_bion_svc = OutputBionService()

# stopwords mínimas de português pra não poluir o ranking com preposições
_STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "no", "na",
    "com", "sem", "por", "para", "que", "há", "ha", "desde", "um", "uma",
}


def _tokenizar(texto: str) -> list[str]:
    """Palavras minúsculas do texto, sem stopwords e com mais de 2 letras."""
    palavras = re.findall(r"[a-zà-ú]+", texto.lower())
    return [p for p in palavras if p not in _STOPWORDS and len(p) > 2]


class EstatisticasInputProtocolo:

    def queixas_mais_frequentes(self, id_empresa, dias=30, top=15):
        """Ranking aproximado de termos mais citados em queixa_principal (C5).

        Importante: isso é frequência de PALAVRAS, não de frases exatas
        -- texto livre não tem padronização, então "dor de cabeça" e
        "cefaleia" contam como termos diferentes. Serve como direção
        geral, não como estatística médica precisa. Se no futuro
        quiserem algo mais preciso, o caminho é a equipe clínica adotar
        um campo estruturado (dropdown de queixas padronizadas) em vez
        de texto livre -- fora do escopo desta função.

        Retorna: {"termos": [{"termo", "total"}, ...], "total_queixas_analisadas": int, "leitura": str}
        """
        queixas = _output_bion_svc.queixas_recentes(id_empresa=id_empresa, dias=dias)

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