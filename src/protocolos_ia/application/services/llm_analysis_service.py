"""Este arquivo orquestra a análise por LLM: contexto seguro, estratégia, chamada resiliente, validação, persistência e auditoria.

Regras: falha do lado da IA vira fallback explícito e nunca é persistida como análise válida; erro de dados
de entrada (422) e de autorização (403/404) sobem sem alteração; só uma resposta validada é gravada.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from ...domain.context.dados_avulsos_adapter import contexto_de_dados_avulsos
from ...domain.context.snapshot_adapter import contexto_de_snapshot
from ...domain.exceptions import (
    CATEGORIA_CONFIGURACAO_INVALIDA,
    CATEGORIA_LLM_INDISPONIVEL,
    CATEGORIA_RESPOSTA_INVALIDA,
    FalhaLLMError,
)
from ...domain.ports.prompt_source import PromptSource
from ...domain.schemas.auditoria import RegistroAuditoriaLLM
from ...domain.strategies.registro import obter_strategy
from ..dto.analysis_request import LLMAnalysisRequest
from ..dto.analysis_result import LLMAnalysisResult
from ..ports.audit_sink import AuditSink
from ..ports.llm_provider import ExecutorLLM, LLMProvider, ParserResposta
from ..ports.output_repository import AutorRequisicao, EnvioAberto, OutputRepository

logger = logging.getLogger("bion.ia.analise")

_STATUS_POR_CATEGORIA = {
    CATEGORIA_RESPOSTA_INVALIDA: "erro_schema",
    CATEGORIA_CONFIGURACAO_INVALIDA: "configuracao",
    CATEGORIA_LLM_INDISPONIVEL: "erro_provider",
}


class LLMAnalysisService:
    def __init__(
        self,
        *,
        provider_factory: Callable[[], LLMProvider],
        prompt_source: PromptSource,
        repo: OutputRepository,
        audit: AuditSink,
        executor: ExecutorLLM,
        parser: ParserResposta,
        versao_prompt: str,
        temperatura: float,
        estimar_custo: Callable[[str, int, int], float],
        relogio: Callable[[], float] = time.monotonic,
    ):
        self._provider_factory = provider_factory
        self._prompt_source = prompt_source
        self._repo = repo
        self._audit = audit
        self._executor = executor
        self._parser = parser
        self._versao_prompt = versao_prompt
        self._temperatura = temperatura
        self._estimar_custo = estimar_custo
        self._relogio = relogio

    def analisar(self, requisicao: LLMAnalysisRequest, autor: AutorRequisicao) -> LLMAnalysisResult:
        """Esta função executa a análise e devolve o resultado. Levanta apenas erros de entrada, autorização ou persistência."""
        estrategia = obter_strategy(requisicao.tipo_analise)

        envio: Optional[EnvioAberto] = None
        if requisicao.vinculada:
            envio = self._repo.abrir_envio(requisicao.id_input_protocolo, autor)
            contexto = contexto_de_snapshot(envio.snapshot)
        else:
            contexto = contexto_de_dados_avulsos(**requisicao.dados_clinicos())
        estrategia.validar_contexto(contexto)

        inicio = self._relogio()
        provider: Optional[LLMProvider] = None
        try:
            provider = self._provider_factory()
            llm_request = estrategia.montar_request(contexto, self._prompt_source, self._versao_prompt)
            bruto = self._executor(provider, llm_request)
            resposta = self._parser.parsear(bruto.texto)
        except FalhaLLMError as falha:
            return self._fallback(requisicao, provider, falha, envio, self._latencia(inicio))

        latencia = self._latencia(inicio)
        modelo = f"{provider.nome_provedor}/{provider.nome_modelo}"[:50]
        registro = None
        if envio is not None:
            registro = self._repo.gravar_resposta(
                envio,
                {
                    **resposta.para_dict_persistencia(),
                    "llm_disponivel": True,
                    "simulado": provider.simulado,
                    "tipo_analise": requisicao.tipo_analise,
                    "versao_prompt": self._versao_prompt,
                },
                modelo,
            )
        self._auditar(
            RegistroAuditoriaLLM(
                provedor=provider.nome_provedor,
                modelo=provider.nome_modelo,
                versao_prompt=self._versao_prompt,
                tipo_analise=requisicao.tipo_analise,
                temperatura=self._temperatura,
                tokens_entrada=bruto.tokens_entrada,
                tokens_saida=bruto.tokens_saida,
                latencia_ms=latencia,
                custo_estimado_usd=self._estimar_custo(provider.nome_modelo, bruto.tokens_entrada, bruto.tokens_saida),
                status="sucesso",
                simulado=provider.simulado,
                uuid_output=registro.uuid if registro else None,
            )
        )
        return LLMAnalysisResult(
            llm_disponivel=True,
            persistido=registro is not None,
            tipo_analise=requisicao.tipo_analise,
            versao_prompt=self._versao_prompt,
            versao_modelo_ia=modelo,
            simulado=provider.simulado,
            resposta=resposta,
            uuid_output=registro.uuid if registro else None,
            versao_input_model=registro.versao_input_model if registro else None,
            criado_em=registro.criado_em if registro else None,
            indice_completude=registro.indice_completude if registro else None,
            indice_confianca=registro.indice_confianca if registro else None,
        )

    def _fallback(self, requisicao, provider, falha: FalhaLLMError, envio, latencia: int) -> LLMAnalysisResult:
        logger.warning(
            "analise_llm_indisponivel",
            extra={"categoria": falha.categoria, "detalhe": falha.detalhes, "tipo_analise": requisicao.tipo_analise},
        )
        nome_provedor = provider.nome_provedor if provider else "indefinido"
        nome_modelo = provider.nome_modelo if provider else "indefinido"
        self._auditar(
            RegistroAuditoriaLLM(
                provedor=nome_provedor,
                modelo=nome_modelo,
                versao_prompt=self._versao_prompt,
                tipo_analise=requisicao.tipo_analise,
                temperatura=self._temperatura,
                latencia_ms=latencia,
                status="circuit_breaker" if falha.detalhes == "circuit_breaker_aberto"
                else _STATUS_POR_CATEGORIA.get(falha.categoria, "erro_provider"),
                categoria_falha=falha.categoria,
                simulado=bool(provider and provider.simulado),
                uuid_output=envio.uuid if envio else None,
            )
        )
        return LLMAnalysisResult(
            llm_disponivel=False,
            persistido=False,
            tipo_analise=requisicao.tipo_analise,
            versao_prompt=self._versao_prompt,
            versao_modelo_ia=f"fallback/{nome_provedor}",
            simulado=bool(provider and provider.simulado),
            categoria_falha=falha.categoria,
            uuid_output=envio.uuid if envio else None,
            versao_input_model=envio.versao_input_model if envio else None,
            criado_em=envio.criado_em if envio else None,
        )

    def _latencia(self, inicio: float) -> int:
        return max(0, int((self._relogio() - inicio) * 1000))

    def _auditar(self, registro: RegistroAuditoriaLLM) -> None:
        """A auditoria é observabilidade. Se falhar, o fluxo clínico segue e apenas o tipo do erro é logado."""
        try:
            self._audit.registrar(registro)
        except Exception as exc:
            logger.error("falha_ao_auditar_chamada_llm", extra={"tipo_erro": type(exc).__name__})
