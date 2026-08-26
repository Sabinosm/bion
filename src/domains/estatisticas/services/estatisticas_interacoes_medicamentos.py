from src.domains.medicamentos.service  import InteracoesMedicamentosService

im_svc = InteracoesMedicamentosService()


class EstatisticasInteracoesMedicamentos:

    # --- D1: Interações medicamentosas cadastradas por gravidade ---
    def por_gravidade(self):
        """Retorna: {"por_gravidade": {...}, "total": int, "leitura": str}

        Nota: catálogo de referência, não muda por empresa/período --
        não recebe id_empresa nem dias de propósito.
        """
        por_gravidade = im_svc.contar_por_gravidade()
        total = sum(por_gravidade.values())

        leitura = f"{total} interações medicamentosas catalogadas na base de conhecimento" if total else None

        return {"por_gravidade": por_gravidade, "total": total, "leitura": leitura}