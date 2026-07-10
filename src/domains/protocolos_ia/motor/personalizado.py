"""Protocolo Personalizado (regras configuráveis por instituição/módulo)."""

from .base import IProtocoloConsulta, InputConsulta, ResultadoConsulta


class ProtocoloPersonalizado(IProtocoloConsulta):
    """Implementação Strategy de um protocolo com regras configuráveis via input_json."""

    VERSAO = "PP-1.0"

    def executar(self, inp: InputConsulta) -> ResultadoConsulta:
        """Avalia as regras configuradas e retorna as ações das que foram disparadas."""
        regras = inp.input_json.get("regras_avaliadas", [])
        alertas = [r["acao"] for r in regras if r.get("disparada")]
        return ResultadoConsulta(alertas=alertas, indice_confianca=0.75)

    def validar_input(self, i):
        """Protocolo personalizado não exige dados mínimos fixos."""
        return True

    def get_nome(self):
        """Retorna o nome de exibição do protocolo."""
        return "ProtocoloPersonalizado"

    def get_versao(self):
        """Retorna a versão/edição do protocolo implementada."""
        return self.VERSAO
