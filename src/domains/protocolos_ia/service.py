"""Este arquivo reúne os casos de uso determinísticos do domínio de IA e a consulta de resultados (OutputBion).

executar_protocolo roda o motor determinístico do host (Strategy/Factory) sem alterá-lo. Quando recebe
id_input_protocolo, persiste o resultado pela mesma trilha de envio usada pela IA generativa.
"""
from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Dict, Optional

from src.core.exceptions import DadosInvalidosError, RecursoNaoEncontradoError
from .application.ports.output_repository import AutorRequisicao, OutputRepository
from .motor.base import InputConsulta, InputTriagem
from .motor.factory import ProtocoloFactory

if TYPE_CHECKING:
    from .repository import OutputBionRepository


class OutputBionService:
    """Casos de uso de execução de protocolos e consulta de resultados de IA."""

    def __init__(
        self,
        repo: Optional[OutputBionRepository] = None,
        protocolo_repo=None,
        factory: Optional[ProtocoloFactory] = None,
        persistencia: Optional[OutputRepository] = None,
    ):
        if repo is None:
            from .repository import OutputBionRepository as RepositorioSaida
            repo = RepositorioSaida()
        if protocolo_repo is None:
            from src.domains.protocolo.shared.repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository
            protocolo_repo = ProtocoloCatalogoRepository()
        self.repo = repo
        self.protocolo_repo = protocolo_repo
        self.factory = factory or ProtocoloFactory()
        self._persistencia = persistencia

    def _obter_persistencia(self) -> OutputRepository:
        if self._persistencia is None:
            from .infrastructure.repositories.output_bion_adapter import OutputBionAdapter

            self._persistencia = OutputBionAdapter(repositorio=self.repo)
        return self._persistencia

    def buscar_por_uuid(self, uuid: str, id_empresa: int):
        """Devolve o OutputBion do UUID dentro da empresa, ou levanta RecursoNaoEncontradoError."""
        output = self.repo.find_by_uuid(uuid, id_empresa)
        if not output:
            raise RecursoNaoEncontradoError("OutputBion não encontrado.")
        return output

    def buscar_output_triagem(self, consulta_uuid: str, id_empresa: int):
        """Devolve o resultado vigente da triagem da consulta. Envio sem resposta não é resultado."""
        output = self.repo.find_output_triagem_da_consulta(consulta_uuid, id_empresa)
        if not output or output.output_ia_json is None:
            raise RecursoNaoEncontradoError("Nenhum resultado de IA encontrado para a triagem desta consulta.")
        return output

    def executar_protocolo(
        self,
        sigla_protocolo: str,
        dados_input: Dict[str, Any],
        id_input_protocolo: Optional[int] = None,
        autor: Optional[AutorRequisicao] = None,
    ) -> Dict[str, Any]:
        """Executa o protocolo e devolve o resultado no formato de OutputBion.to_dict() mais o campo persistido.

        Raises:
            RecursoNaoEncontradoError: protocolo inexistente ou input de outra empresa.
            DadosInvalidosError: entrada malformada, protocolo sem motor ou dados insuficientes.
        """
        if not isinstance(dados_input, dict):
            raise DadosInvalidosError("O corpo da requisição deve ser um objeto JSON.")
        input_json = dados_input.get("input_json", {})
        sinais = dados_input.get("sinais_vitais", [])
        if not isinstance(input_json, dict) or not isinstance(sinais, list):
            raise DadosInvalidosError("input_json deve ser um objeto e sinais_vitais uma lista.")
        for posicao, sinal in enumerate(sinais):
            if not isinstance(sinal, dict) or not isinstance(sinal.get("tipo_parametro"), str) or isinstance(
                sinal.get("valor_numerico"), bool
            ) or not isinstance(sinal.get("valor_numerico"), (int, float)):
                raise DadosInvalidosError(
                    f"sinais_vitais: item {posicao} deve ter tipo_parametro e valor_numerico numérico.",
                    campo="sinais_vitais",
                )
        if id_input_protocolo is not None and (isinstance(id_input_protocolo, bool) or not isinstance(id_input_protocolo, int)):
            raise DadosInvalidosError("id_input_protocolo deve ser um inteiro.", campo="id_input_protocolo")

        catalogo = self.protocolo_repo.find_by_sigla(sigla_protocolo)
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {sigla_protocolo}")
        try:
            motor = self.factory.criar(catalogo)
        except ValueError:
            raise DadosInvalidosError("Protocolo sem motor de execução implementado.", campo="sigla_protocolo") from None

        if catalogo.escopo_uso == "consulta":
            entrada = InputConsulta(input_json=input_json, sinais_vitais=sinais)
        else:
            entrada = InputTriagem(
                input_json=input_json, sinais_vitais=sinais, queixa_principal=dados_input.get("queixa_principal")
            )
        if not motor.validar_input(entrada):
            raise DadosInvalidosError("Dados insuficientes para executar este protocolo.")

        resultado = motor.executar(entrada)
        output_json = dataclasses.asdict(resultado) if dataclasses.is_dataclass(resultado) else dict(resultado)
        versao = (motor.get_versao() or "")[:50]
        confianca = getattr(resultado, "indice_confianca", None)

        if id_input_protocolo is None:
            return {
                "uuid": None, "versao_input_model": None, "output_ia": output_json,
                "versao_modelo_ia": versao, "indice_completude": None, "indice_confianca": confianca,
                "criado_em": None, "persistido": False,
            }
        if autor is None:
            raise DadosInvalidosError("Autor da requisição ausente.")
        persistencia = self._obter_persistencia()
        envio = persistencia.abrir_envio(id_input_protocolo, autor)
        registro = persistencia.gravar_resposta(envio, output_json, versao, None, confianca)
        return {
            "uuid": registro.uuid, "versao_input_model": registro.versao_input_model, "output_ia": output_json,
            "versao_modelo_ia": versao, "indice_completude": registro.indice_completude,
            "indice_confianca": registro.indice_confianca, "criado_em": registro.criado_em, "persistido": True,
        }

    def media_confianca(self, id_empresa: int, dias: int = 30):
        return self.repo.media_confianca(id_empresa=id_empresa, dias=dias)

    def media_confianca_periodo(self, id_empresa, data_inicio, data_fim):
        return self.repo.media_confianca_periodo(id_empresa=id_empresa, data_inicio=data_inicio, data_fim=data_fim)

    def media_completude(self, id_empresa: int, dias: int = 30):
        return self.repo.media_completude(id_empresa=id_empresa, dias=dias)

    def media_completude_periodo(self, id_empresa, data_inicio, data_fim):
        return self.repo.media_completude_periodo(id_empresa=id_empresa, data_inicio=data_inicio, data_fim=data_fim)

    def versoes_em_uso(self, id_empresa: int, dias: int = 30):
        return self.repo.versoes_em_uso(id_empresa=id_empresa, dias=dias)

    def pares_completude_confianca(self, id_empresa: int, dias: int = 30):
        return self.repo.pares_completude_confianca(id_empresa=id_empresa, dias=dias)

    def queixas_recentes(self, id_empresa: int, dias: int = 30, limite: int = 200):
        return self.repo.queixas_recentes(id_empresa=id_empresa, dias=dias, limite=limite)
