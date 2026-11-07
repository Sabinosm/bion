"""gemini.py

Provedor Gemini (SDK google-genai) da avaliação. Traduz a conversa neutra para o formato do Gemini,
faz a chamada pelo executor resiliente (retry só em falha transitória, backoff e circuit breaker por
provedor e modelo, os mesmos do caminho Anthropic) e devolve o turno no formato neutro.

Pontos do Gemini que este adaptador trata (conferidos na documentação do Gemini):
- Chamada de ferramenta manual: o laço é do avaliador (automatic_function_calling desligado).
- Modelos 3+ EXIGEM devolver o turno original da IA (com `thought_signature`) ao responder uma
  chamada de ferramenta, senão a API retorna 400. Por isso o turno vai no campo opaco do turno e é
  reenviado como está. Chamadas paralelas: todas as chamadas juntas, depois TODAS as respostas num
  único turno do usuário.
- Saída estruturada (JSON) junto de ferramentas só existe nos modelos Gemini 3: por padrão o esquema
  só é imposto quando não há ferramentas (fase final); `ferramentas_com_esquema=True` liga nos dois
  (use com modelo 3+). Nas demais, o JSON pode vir cercado por ```: o validador da resposta remove.
- Nomes de modelo mudam: nunca ficam no código, vêm de configuração.

Classificação de falhas: HTTP 408/429/5xx, timeout e queda de conexão são transitórios (retry); demais
4xx são permanentes (sem retry, não abrem o breaker); resposta sem conteúdo ou bloqueada é resposta
inválida. As falhas do SDK nunca são encadeadas nas exceções levantadas, para que corpo de erro e chave
não cheguem aos logs.

NÃO foi executado contra a API real (sem chave neste ambiente); o teste usa o SDK com cliente falso.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..cliente import ClienteIABase, PedidoFerramenta, RequisicaoTurno, TurnoIA, UsoIA
from ..exceptions import (
    ErroPermanenteProvedor,
    ErroTransitorioProvedor,
    ProvedorIndisponivelError,
    RespostaLLMInvalidaError,
)
from ..fabrica import ConfigIAInvalida, provedor
from ..http_anthropic import retry_after
from ..raw_response import RawLLMResponse
from ..resilience import ExecutorResiliente, executor_do_ambiente
from .esquema import para_gemini

SEM_ID = "sem-id:"      # id sintético: o Gemini nem sempre devolve id na chamada

_NOMES_TIMEOUT = {"TimeoutError", "TimeoutException", "Timeout"}
_NOMES_CONEXAO = {"ConnectionError", "TransportError", "NetworkError"}
_HTTP_TRANSITORIOS = {408, 429}


def _types():
    from google.genai import types
    return types


@dataclass(frozen=True, repr=False)     # repr herdado: não expõe o conteúdo clínico do turno
class RawGemini(RawLLMResponse):
    conteudo: Any = None                # turno original do SDK, devolvido na conversa (thought_signature)
    versao_modelo: str | None = None    # model_version informado pela API, sem fallback


def _nome(valor) -> str | None:
    if valor is None:
        return None
    return getattr(valor, "name", None) or str(valor)


def _inteiro(valor) -> int:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else 0


def _classificar(exc: Exception) -> ProvedorIndisponivelError:
    """Converte uma falha do SDK em erro classificado, sem carregar a mensagem original."""
    codigo = getattr(exc, "code", None)
    if isinstance(codigo, int) and not isinstance(codigo, bool) and 100 <= codigo <= 599:
        if codigo in _HTTP_TRANSITORIOS or codigo >= 500:
            return ErroTransitorioProvedor(f"http_{codigo}", retry_after(getattr(exc, "response", None)))
        return ErroPermanenteProvedor(detalhes=f"http_{codigo}")
    nomes = {c.__name__ for c in type(exc).__mro__}
    if nomes & _NOMES_TIMEOUT:
        return ErroTransitorioProvedor("timeout")
    if nomes & _NOMES_CONEXAO:
        return ErroTransitorioProvedor("erro_de_conexao")
    return ProvedorIndisponivelError(detalhes=f"erro_{type(exc).__name__}")


@provedor("gemini")
class ClienteGemini(ClienteIABase):
    provedor = "gemini"
    nome_provedor = "gemini"
    simulado = False

    def __init__(self, modelo: str | None = None, api_key: str | None = None, *, sdk: Any = None,
                 temperatura: float = 0.2, timeout_s: int = 60, ferramentas_com_esquema: bool = False,
                 executor: ExecutorResiliente | None = None):
        if not modelo:
            raise ConfigIAInvalida("Gemini: informe o modelo (BION_IA_MODELO).")
        self.modelo = modelo
        self.temperatura = temperatura
        self.timeout_s = timeout_s
        self.ferramentas_com_esquema = ferramentas_com_esquema
        self._sdk = sdk
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if sdk is None and not self._api_key:
            raise ConfigIAInvalida("Gemini: defina GEMINI_API_KEY.")
        self._executor = executor or executor_do_ambiente()

    @property
    def versao(self) -> str:
        return f"gemini:{self.modelo}"

    @property
    def nome_modelo(self) -> str:
        return self.modelo

    def _cliente(self):
        if self._sdk is None:
            from google import genai
            self._sdk = genai.Client(api_key=self._api_key)
        return self._sdk

    # --------------------------------------------------------------- turno
    def turno(self, conversa: list[dict], ferramentas: list[dict], casca: dict) -> TurnoIA:
        bruto = self._executor(self, RequisicaoTurno(conversa, ferramentas, casca))
        chamadas = [b for b in bruto.blocos_conteudo if b.get("type") == "tool_use"]
        if chamadas:
            pedidos = tuple(PedidoFerramenta(id=b["id"], nome=b["name"], argumentos=b["input"]) for b in chamadas)
            return TurnoIA(pedidos=pedidos, versao_modelo=bruto.versao_modelo, bruto=bruto.conteudo, uso=self._uso(bruto))
        return TurnoIA(resposta=bruto.texto or None, versao_modelo=bruto.versao_modelo, bruto=bruto.conteudo,
                       uso=self._uso(bruto))

    def _uso(self, bruto: RawGemini) -> UsoIA:
        return UsoIA("gemini", self.modelo, bruto.tokens_entrada, bruto.tokens_saida, self.temperatura)

    # ------------------------------------------- uma chamada ao SDK (sem retry)
    def executar(self, request: RequisicaoTurno) -> RawGemini:
        try:
            t = _types()
            sistema, contents = self._traduzir(request.conversa)
            cfg: dict[str, Any] = {
                "system_instruction": sistema,
                "temperature": self.temperatura,
                "automatic_function_calling": t.AutomaticFunctionCallingConfig(disable=True),
                "http_options": t.HttpOptions(timeout=self.timeout_s * 1000),
            }
            if request.ferramentas:
                cfg["tools"] = [t.Tool(function_declarations=[
                    t.FunctionDeclaration(name=f["name"], description=f["description"],
                                          parameters_json_schema=para_gemini(f["input_schema"]))
                    for f in request.ferramentas])]
            if not request.ferramentas or self.ferramentas_com_esquema:
                cfg["response_mime_type"] = "application/json"
                cfg["response_json_schema"] = para_gemini(request.casca)
            config = t.GenerateContentConfig(**cfg)
        except (TypeError, ValueError, KeyError):
            raise ErroPermanenteProvedor(detalhes="requisicao_invalida") from None

        try:
            resp = self._cliente().models.generate_content(model=self.modelo, contents=contents, config=config)
        except Exception as exc:
            raise _classificar(exc) from None
        return self._ler(resp)

    # ---------------------------------------------------- neutro -> Gemini
    def _traduzir(self, conversa: list[dict]):
        t = _types()
        sistema: list[str] = []
        contents: list = []

        def usuario(parts):
            if contents and getattr(contents[-1], "role", None) == "user":
                contents[-1].parts.extend(parts)        # nunca dois turnos seguidos do mesmo papel
            else:
                contents.append(t.Content(role="user", parts=parts))

        for m in conversa:
            papel = m["papel"]
            if papel == "sistema":
                sistema.append(m["conteudo"])
            elif papel == "usuario":
                usuario([t.Part(text=m["conteudo"])])
            elif papel == "ia":
                if m.get("bruto") is not None:
                    contents.append(m["bruto"])         # turno original, com assinaturas
                elif m.get("pedidos"):
                    contents.append(t.Content(role="model", parts=[
                        t.Part(function_call=t.FunctionCall(
                            name=p["nome"], args=p["argumentos"],
                            id=None if p["id"].startswith(SEM_ID) else p["id"]))
                        for p in m["pedidos"]]))
                else:
                    contents.append(t.Content(role="model", parts=[t.Part(text=m.get("conteudo") or "(sem resposta)")]))
            elif papel == "ferramenta":
                pid = m["pedido_id"]
                usuario([t.Part(function_response=t.FunctionResponse(
                    name=m["nome"], response=m["conteudo"], id=None if pid.startswith(SEM_ID) else pid))])
        return "\n\n".join(sistema) or None, contents

    # ---------------------------------------------------- Gemini -> bruto
    def _ler(self, resp) -> RawGemini:
        cands = getattr(resp, "candidates", None) or []
        content = cands[0].content if cands else None
        motivo = _nome(getattr(cands[0], "finish_reason", None)) if cands else None
        if content is None or not content.parts:
            bloqueio = _nome(getattr(getattr(resp, "prompt_feedback", None), "block_reason", None))
            raise RespostaLLMInvalidaError(f"sem_resposta:bloqueio={bloqueio}:finish_reason={motivo}")

        chamadas = [p.function_call for p in content.parts if p.function_call]
        blocos = tuple({"type": "tool_use", "id": c.id or f"{SEM_ID}{c.name}:{i}", "name": c.name,
                        "input": dict(c.args or {})} for i, c in enumerate(chamadas))
        texto = "".join(p.text for p in content.parts if p.text and not p.thought).strip()
        versao = getattr(resp, "model_version", None)
        uso = getattr(resp, "usage_metadata", None)
        return RawGemini(
            texto=texto,
            modelo=versao or self.modelo,
            tokens_entrada=_inteiro(getattr(uso, "prompt_token_count", 0)),
            tokens_saida=_inteiro(getattr(uso, "candidates_token_count", 0)),
            motivo_parada=motivo,
            blocos_conteudo=blocos,
            conteudo=content,
            versao_modelo=versao,
        )
