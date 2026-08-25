from src.domains.dados_clinicos.service import DadosClinicosService

dcs = DadosClinicosService()


class EstatisticasColetaClinica:

    # --- C4: Tempo até busca por atendimento (sintoma -> consulta) ---
    def tempo_ate_atendimento(self, id_empresa, dias=30):
        """Retorna: {"media_horas": float|None, "leitura": str}"""
        media = dcs.media_horas_ate_atendimento(id_empresa=id_empresa, dias=dias)

        leitura = None
        if media is not None:
            if media < 24:
                leitura = f"Pacientes buscam atendimento em média {round(media, 1)}h após início dos sintomas"
            else:
                dias_media = round(media / 24, 1)
                leitura = f"Pacientes buscam atendimento em média {dias_media} dias após início dos sintomas"

        return {"media_horas": round(media, 1) if media is not None else None, "leitura": leitura}