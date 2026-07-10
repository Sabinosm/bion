"""
Regras de negocio do dominio Protocolos / IA.

CORRECAO APLICADA: `ia/controller.py` original chamava
`_svc.buscar_output_triagem(consulta_uuid)`, metodo que nunca existia em
`OutputBionService` -- a rota `/output-triagem/<consulta_uuid>` quebrava
com AttributeError sempre que era chamada. Implementado aqui de fato,
delegando a navegacao de relacionamentos para o repository (ver
`find_output_triagem_da_consulta`).

`executar_protocolo` e o metodo novo que efetivamente liga o
ProtocoloCatalogo (dado persistido) ao motor Strategy/Factory
(`src/domains/protocolos_ia/motor/`), que antes existia mas nunca era
chamado por nenhum service -- so os motores ficavam soltos no filesystem.
"""

from datetime import datetime, timezone, date

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .repository import (
    ProtocoloCatalogoRepository, OutputBionRepository,
    CatalogoFluxogramasMtsRepository, CatalogoModulosRepository,
)
from .motor.factory import ProtocoloFactory
from .motor.base import InputTriagem, InputConsulta, ResultadoTriagem
from .motor.ia_base import ContextoClinico
from .motor.llm_motor import LlmMotor


def _parse_data(valor):
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")


class ProtocoloCatalogoService:

    def __init__(self):
        self.repo = ProtocoloCatalogoRepository()

    def buscar_por_uuid(self, uuid: str):
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {uuid}")
        return e

    def buscar_por_id(self, id:int):
        e = self.repo.find_by_id(id)
        if not e:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado {id}")
    
    def listar(self):
        return self.repo.find_all()

    def criar(self, dados: dict):
        from src.models.protocolos import ProtocoloCatalogo
        obrigatorios = ("nome_protocolo", "sigla", "tipo_resultado",
                        "versao_vigente", "data_vigencia")
        faltando = [c for c in obrigatorios if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")
        if self.repo.find_by_sigla(dados["sigla"]):
            raise DadosInvalidosError(f"Já existe um protocolo com a sigla {dados['sigla']}.")

        p = ProtocoloCatalogo(
            nome_protocolo=dados["nome_protocolo"],
            sigla=dados["sigla"],
            tipo_resultado=dados["tipo_resultado"],
            tipo_protocolo=dados.get("tipo_protocolo"),
            escopo_populacao=dados.get("escopo_populacao", "universal"),
            escopo_uso=dados.get("escopo_uso", "ambos"),
            versao_vigente=dados["versao_vigente"],
            data_vigencia=_parse_data(dados["data_vigencia"]),
            referencia_bibliografica=dados.get("referencia_bibliografica"),
            orgao_emissor=dados.get("orgao_emissor"),
            flag_personalizado=bool(dados.get("flag_personalizado", False)),
        )
        return self.repo.save(p)


class OutputBionService:

    def __init__(self):
        self.repo = OutputBionRepository()
        self.protocolo_repo = ProtocoloCatalogoRepository()
        self.factory = ProtocoloFactory()

    def buscar_por_uuid(self, uuid: str):
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"OutputBion não encontrado: {uuid}")
        return e

    def buscar_output_triagem(self, consulta_uuid: str):
        output = self.repo.find_output_triagem_da_consulta(consulta_uuid)
        if not output:
            raise RecursoNaoEncontradoError(
                f"Nenhum resultado de IA encontrado para a triagem da consulta {consulta_uuid}."
            )
        return output

    def executar_protocolo(self, sigla_protocolo: str, dados_input: dict, id_input_protocolo: int = None):
        """
        Instancia o motor certo via Factory (Strategy), executa e persiste
        o resultado como OutputBion. `dados_input` deve conter as chaves
        esperadas pelo motor (`input_json`, `sinais_vitais`, `queixa_principal`),
        conforme o protocolo escolhido.
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

    def analisar_com_llm(self, contexto: ContextoClinico, id_input_protocolo: int = None):
        """
        Suporte adicional de IA generativa (Claude via API), complementar
        aos protocolos deterministicos. Usado tipicamente na avaliacao
        medica, apos a triagem, para sugerir diagnosticos/condutas com
        base no contexto clinico completo do atendimento. Requer
        LLM_API_KEY configurada (.env); a decisao final permanece sempre
        do profissional de saude.
        """
        motor = LlmMotor()
        resultado_json = motor.analisar(contexto)

        from src.models.protocolos import OutputBion
        output = OutputBion(
            id_input=id_input_protocolo,
            output_ia_json=resultado_json,
            versao_modelo_ia=f"{motor.get_nome_modelo()}-{motor.get_versao()}",
            indice_completude=None,
            indice_confianca=None,
        )
        return self.repo.save(output)


class CatalogoFluxogramasMtsService:

    def __init__(self):
        self.repo = CatalogoFluxogramasMtsRepository()

    def buscar_por_uuid(self, uuid: str):
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Fluxograma MTS não encontrado: {uuid}")
        return e

    def listar(self):
        return self.repo.find_all()


class CatalogoModulosService:

    def __init__(self):
        self.repo = CatalogoModulosRepository()

    def buscar_por_uuid(self, uuid: str):
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Módulo não encontrado: {uuid}")
        return e

    def listar(self):
        return self.repo.find_all()
