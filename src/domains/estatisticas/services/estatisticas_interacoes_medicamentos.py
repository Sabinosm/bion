"""Estatísticas do catálogo de interações medicamentosas cadastradas."""

from src.domains.medicamentos.service import InteracoesMedicamentosService

im_svc = InteracoesMedicamentosService()


class EstatisticasInteracoesMedicamentos:

    def por_gravidade(self):
        """Interações medicamentosas cadastradas, agrupadas por gravidade (D1).

        Nota: catálogo de referência, não muda por empresa/período --
        não recebe id_empresa nem dias de propósito.

        Retorna: {"por_gravidade": {...}, "total": int, "leitura": str}
        """
        por_gravidade = im_svc.contar_por_gravidade()
        total = sum(por_gravidade.values())

        leitura = f"{total} interações medicamentosas catalogadas na base de conhecimento" if total else None

        return {"por_gravidade": por_gravidade, "total": total, "leitura": leitura}
