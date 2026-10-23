"""
estatisticas_interacoes_medicamentos.py

Estatísticas do catálogo de interações medicamentosas cadastradas, agrupadas
por gravidade. É um dado de referência global: não depende de empresa nem de
período.
"""

from src.domains.medicamentos.interacoes.interacoes_medicamentos_service import InteracoesMedicamentosService

_interacoes_svc = InteracoesMedicamentosService()


class EstatisticasInteracoesMedicamentos:

    def por_gravidade(self):
        """Interações medicamentosas cadastradas, agrupadas por gravidade (D1).

        Nota: catálogo de referência, não muda por empresa/período --
        não recebe id_empresa nem dias de propósito.

        Retorna: {"por_gravidade": {...}, "total": int, "leitura": str}
        """
        por_gravidade = _interacoes_svc.contar_por_gravidade()
        total = sum(por_gravidade.values())

        leitura = f"{total} interações medicamentosas catalogadas na base de conhecimento" if total else None

        return {"por_gravidade": por_gravidade, "total": total, "leitura": leitura}