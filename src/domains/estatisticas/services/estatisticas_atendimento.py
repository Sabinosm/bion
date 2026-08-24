from src.domains.atendimento.service import AtendimentoService

ats = AtendimentoService()


def _formatar_duracao(segundos: float) -> str:
    """Converte segundos em 'XminYs' pro texto de leitura."""
    minutos, seg = divmod(int(segundos), 60)
    return f"{minutos}min{seg:02d}s"


class EstatisticasAtendimento:

    # --- A2: Tempo médio de atendimento por tipo ---
    def tempo_medio_por_tipo(self, id_empresa, dias=30):
        """Duração média por tipo_atendimento (triagem, avaliacao-medica, etc).

        Retorna: {"por_tipo": [{"tipo_atendimento", "media_segundos",
                  "media_formatada", "total"}, ...], "leitura": str}

        Nota: variação % vs. período anterior (mencionada na leitura do
        .md) fica pendente -- precisaria de uma segunda chamada com
        dias*2 e comparar as duas janelas. Deixei de fora por ora pra
        não assumir a regra de "período anterior" sem confirmar com
        vocês (dias anteriores consecutivos? mesmo período do mês
        passado?).
        """
        bruto = ats.tempo_medio_por_tipo(id_empresa=id_empresa, dias=dias)

        por_tipo = [
            {
                **item,
                "media_formatada": _formatar_duracao(item["media_segundos"]),
            }
            for item in bruto
        ]

        leitura = None
        if por_tipo:
            principal = max(por_tipo, key=lambda item: item["total"])
            leitura = (
                f"Tempo médio de atendimento ({principal['tipo_atendimento']}): "
                f"{principal['media_formatada']}"
            )

        return {"por_tipo": por_tipo, "leitura": leitura}