"""Protocolo de Triagem Manchester (MTS - 3ª edição)."""

from .base import IProtocoloTriagem, InputTriagem, ResultadoTriagem


class MtsProtocolo(IProtocoloTriagem):
    """Implementação Strategy do Protocolo de Triagem Manchester."""

    VERSAO = "MTS-3ed"
    COR_TEMPO = {"Vermelho": 0, "Laranja": 10, "Amarelo": 60, "Verde": 120, "Azul": 240}

    def executar(self, inp: InputTriagem) -> ResultadoTriagem:
        """
        Avalia os discriminadores do fluxograma escolhido e determina a
        cor de risco e o tempo máximo de espera correspondente.
        """
        fluxo = inp.input_json.get("fluxograma", {})
        discs = fluxo.get("discriminadores", [])
        cor, det = "Verde", None
        for d in discs:
            if d.get("resultado") == "positivo":
                cor = d.get("cor_resultante", "Amarelo")
                det = d.get("nome")
                break
        return ResultadoTriagem(
            cor_mts=cor,
            tempo_max_espera=self.COR_TEMPO.get(cor, 120),
            discriminadores_avaliados=discs,
            discriminante_determinante=det,
        )

    def validar_input(self, i: InputTriagem) -> bool:
        """Exige queixa principal, seja no atributo direto ou dentro de input_json."""
        return bool(i.queixa_principal or i.input_json.get("queixa_principal"))

    def get_nome(self):
        """Retorna o nome de exibição do protocolo."""
        return "MTS"

    def get_versao(self):
        """Retorna a versão/edição do protocolo implementada."""
        return self.VERSAO
