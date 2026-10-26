"""Adaptador entre a infraestrutura LLM do módulo e o contrato ClienteIA do bion-main.

O fluxo novo do host controla ferramentas, validação clínica e persistência. Este adaptador
apenas traduz a conversa neutra para a API Messages da Anthropic e devolve texto ou pedidos
estruturados de ferramenta. Não grava dados clínicos e não executa ferramentas por conta própria.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from .config import ConfiguracaoLLM
from .exceptions import (
    ConfiguracaoLLMInvalidaError,
    ErroPermanenteProvedor,
    ErroTransitorioProvedor,
    RespostaLLMInvalidaError,
)
from .raw_response import RawLLMResponse
from .resilience import ExecutorResiliente

TIMEOUT_CONEXAO_SEGUNDOS = 5.0
RETRY_AFTER_MAXIMO = 30.0


@dataclass(frozen=True)
class RequisicaoTurno:
    conversa: list[dict]
    ferramentas: list[dict]
    casca: dict


def _retry_after(resposta) -> Optional[float]:
    headers = getattr(resposta, "headers", {}) or {}
    bruto = headers.get("retry-after")
    try:
        valor = float(bruto)
    except (TypeError, ValueError):
        return None
    return min(max(valor, 0.0), RETRY_AFTER_MAXIMO)


def _texto_conteudo(valor) -> str:
    if isinstance(valor, str):
        return valor
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"))


def _converter_conversa(conversa: list[dict]) -> tuple[str, list[dict]]:
    """Converte papéis neutros do host para mensagens da API Messages."""
    sistemas: list[str] = []
    mensagens: list[dict] = []
    resultados_ferramentas: list[dict] = []

    def descarregar_resultados() -> None:
        if resultados_ferramentas:
            mensagens.append({"role": "user", "content": list(resultados_ferramentas)})
            resultados_ferramentas.clear()

    for item in conversa:
        if not isinstance(item, dict):
            raise ValueError("formato de conversa inválido")
        papel = item.get("papel")
        if papel == "sistema":
            descarregar_resultados()
            conteudo = item.get("conteudo")
            if isinstance(conteudo, str) and conteudo.strip():
                sistemas.append(conteudo.strip())
            continue

        if papel == "ferramenta":
            pedido_id = item.get("pedido_id")
            nome = item.get("nome")
            if not isinstance(pedido_id, str) or not pedido_id or not isinstance(nome, str) or not nome:
                raise ValueError("retorno de ferramenta sem identificador válido")
            resultados_ferramentas.append({
                "type": "tool_result",
                "tool_use_id": pedido_id,
                "content": _texto_conteudo(item.get("conteudo", {})),
            })
            continue

        descarregar_resultados()
        if papel == "usuario":
            conteudo = item.get("conteudo", "")
            if not isinstance(conteudo, str):
                conteudo = _texto_conteudo(conteudo)
            mensagens.append({"role": "user", "content": conteudo})
        elif papel == "ia" and isinstance(item.get("pedidos"), list):
            blocos = []
            for pedido in item["pedidos"]:
                if not isinstance(pedido, dict):
                    raise ValueError("pedido de ferramenta inválido")
                pedido_id = pedido.get("id")
                nome = pedido.get("nome")
                argumentos = pedido.get("argumentos", {})
                if not isinstance(pedido_id, str) or not pedido_id or not isinstance(nome, str) or not nome:
                    raise ValueError("pedido de ferramenta sem identificador válido")
                if not isinstance(argumentos, dict):
                    raise ValueError("argumentos de ferramenta devem ser um objeto")
                blocos.append({"type": "tool_use", "id": pedido_id, "name": nome, "input": argumentos})
            if blocos:
                mensagens.append({"role": "assistant", "content": blocos})
        elif papel == "ia":
            conteudo = item.get("conteudo", "")
            if not isinstance(conteudo, str):
                conteudo = _texto_conteudo(conteudo)
            if conteudo:
                mensagens.append({"role": "assistant", "content": conteudo})
        else:
            raise ValueError("papel de conversa não suportado")

    descarregar_resultados()
    if not mensagens or not any(m["role"] == "user" for m in mensagens):
        raise ValueError("a conversa precisa conter uma mensagem do usuário")
    return "\n\n".join(sistemas), mensagens


def _schema_ferramentas(ferramentas: list[dict]) -> list[dict]:
    """Remove metadados internos da pool e envia apenas os campos aceitos pela API."""
    saida = []
    for ferramenta in ferramentas:
        if not isinstance(ferramenta, dict):
            raise ValueError("definição de ferramenta inválida")
        nome = ferramenta.get("name")
        descricao = ferramenta.get("description", "")
        schema = ferramenta.get("input_schema")
        if not isinstance(nome, str) or not nome or not isinstance(schema, dict):
            raise ValueError("definição de ferramenta incompleta")
        item = {"name": nome, "input_schema": schema}
        if isinstance(descricao, str) and descricao:
            item["description"] = descricao
        saida.append(item)
    return saida


class ProvedorAnthropicTurno:
    """Faz uma chamada HTTP da API Messages sem registrar conteúdo clínico."""

    nome_provedor = "anthropic"
    simulado = False

    def __init__(self, config: ConfiguracaoLLM, http_post: Optional[Callable] = None):
        self._config = config.validar()
        self._post = http_post or requests.post

    @property
    def nome_modelo(self) -> str:
        return self._config.modelo

    def executar(self, request: RequisicaoTurno) -> RawLLMResponse:
        try:
            sistema, mensagens = _converter_conversa(request.conversa)
            schema = json.dumps(request.casca, ensure_ascii=False, separators=(",", ":"))
            instrucao_schema = (
                "\n\nFormato obrigatório da resposta final: um único objeto JSON que cumpra o JSON Schema abaixo. "
                "Não inclua Markdown nem texto fora do JSON.\nJSON Schema: " + schema
            )
            sistema = (sistema + instrucao_schema).strip()
            corpo = {
                "model": self._config.modelo,
                "max_tokens": self._config.max_tokens,
                "temperature": self._config.temperatura,
                "system": sistema,
                "messages": mensagens,
            }
            tools = _schema_ferramentas(request.ferramentas)
            if tools:
                corpo["tools"] = tools
                corpo["tool_choice"] = {"type": "auto"}
        except (TypeError, ValueError):
            raise ErroPermanenteProvedor(detalhes="requisicao_invalida") from None

        try:
            resposta = self._post(
                self._config.url_base,
                headers={
                    "x-api-key": self._config.api_key,
                    "anthropic-version": self._config.anthropic_version,
                    "content-type": "application/json",
                },
                json=corpo,
                timeout=(TIMEOUT_CONEXAO_SEGUNDOS, self._config.timeout_segundos),
            )
        except requests.exceptions.Timeout:
            raise ErroTransitorioProvedor("timeout") from None
        except requests.exceptions.ConnectionError:
            raise ErroTransitorioProvedor("erro_de_conexao") from None
        except requests.exceptions.RequestException:
            raise ErroPermanenteProvedor(detalhes="requisicao_invalida") from None

        status = getattr(resposta, "status_code", None)
        if status == 429 or (isinstance(status, int) and status >= 500):
            raise ErroTransitorioProvedor(f"http_{status}", _retry_after(resposta))
        if not isinstance(status, int) or status >= 400:
            raise ErroPermanenteProvedor(detalhes=f"http_{status or 'invalido'}")

        try:
            dados = resposta.json()
        except (ValueError, AttributeError):
            raise RespostaLLMInvalidaError("corpo_nao_json") from None
        if not isinstance(dados, dict) or not isinstance(dados.get("content"), list):
            raise RespostaLLMInvalidaError("corpo_inesperado")

        blocos = tuple(b for b in dados["content"] if isinstance(b, dict))
        textos = [b["text"] for b in blocos if b.get("type") == "text" and isinstance(b.get("text"), str)]
        chamadas = [b for b in blocos if b.get("type") == "tool_use"]
        if not textos and not chamadas:
            raise RespostaLLMInvalidaError("sem_conteudo_utilizavel")

        uso = dados.get("usage") if isinstance(dados.get("usage"), dict) else {}
        entrada, saida = uso.get("input_tokens", 0), uso.get("output_tokens", 0)
        return RawLLMResponse(
            texto="\n".join(textos),
            modelo=self._config.modelo,
            tokens_entrada=entrada if isinstance(entrada, int) and not isinstance(entrada, bool) else 0,
            tokens_saida=saida if isinstance(saida, int) and not isinstance(saida, bool) else 0,
            motivo_parada=dados.get("stop_reason") if isinstance(dados.get("stop_reason"), str) else None,
            blocos_conteudo=blocos,
        )


class ClienteIAAnthropic:
    """Implementa ClienteIA do bion-main usando o provedor e a resiliência do módulo."""

    def __init__(
        self,
        config: ConfiguracaoLLM,
        http_post: Optional[Callable] = None,
        executor: Optional[ExecutorResiliente] = None,
    ):
        self._config = config.validar()
        if self._config.provedor != "anthropic":
            raise ConfiguracaoLLMInvalidaError("LLM_PROVIDER", "este cliente exige anthropic")
        self._provedor = ProvedorAnthropicTurno(self._config, http_post=http_post)
        self._executor = executor or ExecutorResiliente(
            max_retries=self._config.max_retries,
            breaker_falhas=self._config.breaker_falhas,
            breaker_reset_segundos=self._config.breaker_reset_segundos,
        )
        self.versao = self._config.modelo

    def turno(self, conversa: list[dict], ferramentas: list[dict], casca: dict):
        from src.domains.avaliacao_bion.helpers.cliente import PedidoFerramenta, TurnoIA

        bruto = self._executor(self._provedor, RequisicaoTurno(conversa, ferramentas, casca))
        blocos = bruto.blocos_conteudo
        chamadas = [b for b in blocos if b.get("type") == "tool_use"]
        if chamadas:
            pedidos = []
            for chamada in chamadas:
                nome = chamada.get("name")
                pedido_id = chamada.get("id")
                argumentos = chamada.get("input", {})
                if not isinstance(nome, str) or not nome or not isinstance(pedido_id, str) or not pedido_id:
                    raise RespostaLLMInvalidaError("chamada_de_ferramenta_invalida")
                if not isinstance(argumentos, dict):
                    raise RespostaLLMInvalidaError("argumentos_de_ferramenta_invalidos")
                pedidos.append(PedidoFerramenta(id=pedido_id, nome=nome, argumentos=argumentos))
            return TurnoIA(pedidos=tuple(pedidos), versao_modelo=bruto.modelo)
        if not bruto.texto.strip():
            raise RespostaLLMInvalidaError("resposta_final_vazia")
        return TurnoIA(resposta=bruto.texto, versao_modelo=bruto.modelo)


class ClienteIAMockAvaliacao:
    """Resposta sintética marcada no detalhe; serve somente para teste e demonstração."""

    versao = "mock-validacao-contrato"

    def turno(self, conversa: list[dict], ferramentas: list[dict], casca: dict):
        from src.domains.avaliacao_bion.helpers.cliente import TurnoIA

        texto_usuario = "\n".join(
            x.get("conteudo", "") for x in conversa
            if isinstance(x, dict) and x.get("papel") == "usuario" and isinstance(x.get("conteudo"), str)
        )
        nomes = list(dict.fromkeys(
            n for n in re.findall(r"(?m)^##\s+([A-Za-z0-9_-]+)\s*$", texto_usuario)
            if n.lower() != "lacunas"
        ))
        blocos = nomes[:20] or ["paciente"]
        resposta = {
            "proposta": {"resultado": None, "medicamentos": [], "exames": []},
            "precisa_mais_informacao": True,
            "perguntas_pendentes": [{
                "pergunta": "Execute com o provedor de IA real antes de qualquer decisão clínica.",
                "motivo": "Esta resposta foi gerada pelo provedor simulado e não representa uma análise clínica.",
                "bloco_relacionado": None,
            }],
            "justificativas_medicamentos": [],
            "detalhamento_explicacao": "Resposta simulada somente para teste de integração. Não usar em atendimento clínico.",
            "blocos_considerados": blocos,
        }
        return TurnoIA(resposta=resposta, versao_modelo=self.versao)


class ClienteIAConfiguravel:
    """Cria o cliente com base no ambiente apenas na primeira chamada do worker."""

    versao = "bion-modulo-ia"

    def __init__(self, carregador_config: Callable[[], ConfiguracaoLLM] = ConfiguracaoLLM.do_ambiente):
        self._carregador_config = carregador_config
        self._cliente = None
        self._lock = threading.Lock()

    def _obter_cliente(self):
        if self._cliente is None:
            with self._lock:
                if self._cliente is None:
                    config = self._carregador_config()
                    if config.provedor == "mock":
                        self._cliente = ClienteIAMockAvaliacao()
                    elif config.provedor == "anthropic":
                        self._cliente = ClienteIAAnthropic(config)
                    else:
                        raise ConfiguracaoLLMInvalidaError("LLM_PROVIDER", "provedor não suportado")
        return self._cliente

    def turno(self, conversa: list[dict], ferramentas: list[dict], casca: dict):
        return self._obter_cliente().turno(conversa, ferramentas, casca)
