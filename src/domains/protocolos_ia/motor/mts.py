"""
Protocolo de Triagem Manchester (MTS - 3a edicao).

CORRECAO APLICADA: `validar_input` chamava `i.queixa_principal`, mas
`InputTriagem` (base.py) so tem o atributo `input_json` -- isso quebraria
com `AttributeError` sempre que a validacao fosse chamada antes de
`executar`. Corrigido para ler `input_json.get("queixa_principal")`.
"""

from .base import IProtocoloTriagem, InputTriagem, ResultadoTriagem


class MtsProtocolo(IProtocoloTriagem):
    VERSAO = "MTS-3ed"
    COR_TEMPO = {"Vermelho": 0, "Laranja": 10, "Amarelo": 60, "Verde": 120, "Azul": 240}

    def executar(self, inp: InputTriagem) -> ResultadoTriagem:
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
        return bool(i.queixa_principal or i.input_json.get("queixa_principal"))

    def get_nome(self):
        return "MTS"

    def get_versao(self):
        return self.VERSAO
