"""Regras de negócio de execução de protocolos determinísticos (Strategy/Factory) e consulta de resultados de IA."""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .repository import OutputBionRepository
from src.domains.protocolo.repository import ProtocoloCatalogoRepository
from .motor.factory import ProtocoloFactory
from .motor.base import InputTriagem, InputConsulta


class OutputBionService:
    """Casos de uso de execução de protocolos e consulta de resultados de IA (OutputBion)."""

    def __init__(self):
        self.repo = OutputBionRepository()
        self.protocolo_repo = ProtocoloCatalogoRepository()
        self.factory = ProtocoloFactory()

    def buscar_por_uuid(self, uuid: str):
        """Retorna um OutputBion pelo UUID ou lança RecursoNaoEncontradoError."""
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"OutputBion não encontrado: {uuid}")
        return e

    def buscar_output_triagem(self, consulta_uuid: str):
        """
        Retorna o OutputBion mais recente gerado na triagem de uma Consulta.

        Raises:
            RecursoNaoEncontradoError: se não houver resultado de IA para a triagem.
        """
        output = self.repo.find_output_triagem_da_consulta(consulta_uuid)
        if not output:
            raise RecursoNaoEncontradoError(
                f"Nenhum resultado de IA encontrado para a triagem da consulta {consulta_uuid}."
            )
        return output

    def executar_protocolo(self, sigla_protocolo: str, dados_input: dict, id_input_protocolo: int = None):
        """
        Instancia o motor certo via Factory (Strategy), executa e persiste
        o resultado como OutputBion.

        Args:
            sigla_protocolo: sigla do ProtocoloCatalogo (ex: 'MTS', 'NEWS2').
            dados_input: deve conter as chaves esperadas pelo motor
                (`input_json`, `sinais_vitais`, `queixa_principal`),
                conforme o protocolo escolhido.
            id_input_protocolo: ID do InputProtocolo de origem, se houver.

        Raises:
            RecursoNaoEncontradoError: se o protocolo não existir.
            DadosInvalidosError: se os dados de entrada forem insuficientes.
        """
        catalogo = self.protocolo_repo.find_by_sigla(sigla_protocolo)
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {sigla_protocolo}")

        motor = self.factory.criar(catalogo)

        if catalogo.escopo_uso == "consulta":
            entrada = InputConsulta(
                input_json=dados_input.get("input_json", {}),
                sinais_vitais=dados_input.get("sinais_vitais", []),
            )
        else:
            entrada = InputTriagem(
                input_json=dados_input.get("input_json", {}),
                sinais_vitais=dados_input.get("sinais_vitais", []),
                queixa_principal=dados_input.get("queixa_principal"),
            )

        if not motor.validar_input(entrada):
            raise DadosInvalidosError("Dados insuficientes para executar este protocolo.")

        resultado = motor.executar(entrada)
        output_json = (
            resultado.__dict__ if hasattr(resultado, "__dict__") else dict(resultado)
        )

        from src.models.protocolos import OutputBion
        output = OutputBion(
            id_input=id_input_protocolo,
            output_ia_json=output_json,
            versao_modelo_ia=motor.get_versao(),
            indice_completude=100.0,
            indice_confianca=getattr(resultado, "indice_confianca", None),
        )
        return self.repo.save(output)
