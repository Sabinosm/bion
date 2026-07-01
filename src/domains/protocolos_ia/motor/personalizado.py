"""Protocolo Personalizado (regras configuraveis por instituicao/modulo)."""

from .base import IProtocoloConsulta, InputConsulta, ResultadoConsulta


class ProtocoloPersonalizado(IProtocoloConsulta):
    VERSAO = "PP-1.0"

    def executar(self, inp: InputConsulta) -> ResultadoConsulta:
        regras = inp.input_json.get("regras_avaliadas", [])
        alertas = [r["acao"] for r in regras if r.get("disparada")]
        return ResultadoConsulta(alertas=alertas, indice_confianca=0.75)

    def validar_input(self, i):
        return True

    def get_nome(self):
        return "ProtocoloPersonalizado"

    def get_versao(self):
        return self.VERSAO
