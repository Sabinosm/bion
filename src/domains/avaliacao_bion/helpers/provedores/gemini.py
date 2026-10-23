"""Estrategia concreta: Gemini (SDK google-genai).

Pontos do Gemini que este adaptador trata (conferidos na documentacao do Gemini):
- Chamada de ferramenta manual: o loop e do avaliador (automatic_function_calling desligado).
- Modelos 3+ EXIGEM devolver o turno original da IA (com `thought_signature`) ao responder
  uma chamada de ferramenta, senao a API retorna 400. Por isso o turno vai em `TurnoIA.bruto`
  e e reenviado como esta. Chamadas paralelas: todas as chamadas juntas, depois TODAS as respostas
  num unico turno do usuario.
- Saida estruturada (JSON) junto de ferramentas so existe nos modelos Gemini 3: por padrao o
  esquema so e imposto quando nao ha ferramentas (fase final); `ferramentas_com_esquema=True`
  liga nos dois (use com modelo 3+). Nas demais, o JSON pode vir cercado por ```: o
  `interpretar` ja remove.
- Nomes de modelo mudam: nunca ficam no codigo, vem de configuracao.

NAO foi executado contra a API real (sem chave neste ambiente); o teste usa o SDK com cliente falso.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from ..cliente import ClienteIABase, ErroIA, PedidoFerramenta, TurnoIA
from ..fabrica import ConfigIAInvalida, provedor
from .esquema import para_gemini

log = logging.getLogger(__name__)

SEM_ID = "sem-id:"      # id sintetico: o Gemini nem sempre devolve id na chamada


def _types():
    from google.genai import types
    return types


@provedor("gemini")
class ClienteGemini(ClienteIABase):
    provedor = "gemini"

    def __init__(self, modelo: str | None = None, api_key: str | None = None, *, sdk: Any = None,
                 temperatura: float = 0.2, timeout_s: int = 90, ferramentas_com_esquema: bool = False):
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

    @property
    def versao(self) -> str:
        return f"gemini:{self.modelo}"

    def _cliente(self):
        if self._sdk is None:
            from google import genai
            self._sdk = genai.Client(api_key=self._api_key)
        return self._sdk

    # --------------------------------------------------------------- turno
    def turno(self, conversa: list[dict], ferramentas: list[dict], casca: dict) -> TurnoIA:
        t = _types()
        sistema, contents = self._traduzir(conversa)
        cfg: dict[str, Any] = {
            "system_instruction": sistema,
            "temperature": self.temperatura,
            "automatic_function_calling": t.AutomaticFunctionCallingConfig(disable=True),
            "http_options": t.HttpOptions(timeout=self.timeout_s * 1000),
        }
        if ferramentas:
            cfg["tools"] = [t.Tool(function_declarations=[
                t.FunctionDeclaration(name=f["name"], description=f["description"],
                                      parameters_json_schema=para_gemini(f["input_schema"]))
                for f in ferramentas])]
        if not ferramentas or self.ferramentas_com_esquema:
            cfg["response_mime_type"] = "application/json"
            cfg["response_json_schema"] = para_gemini(casca)
        resp = self._cliente().models.generate_content(
            model=self.modelo, contents=contents, config=t.GenerateContentConfig(**cfg))
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

    # ---------------------------------------------------- Gemini -> neutro
    def _ler(self, resp) -> TurnoIA:
        cands = getattr(resp, "candidates", None) or []
        content = cands[0].content if cands else None
        if content is None or not content.parts:
            bloqueio = getattr(getattr(resp, "prompt_feedback", None), "block_reason", None)
            motivo = getattr(cands[0], "finish_reason", None) if cands else None
            raise ErroIA(f"Gemini sem resposta (bloqueio={bloqueio}, finish_reason={motivo})")
        versao = getattr(resp, "model_version", None)
        chamadas = [p.function_call for p in content.parts if p.function_call]
        if chamadas:
            pedidos = tuple(PedidoFerramenta(id=c.id or f"{SEM_ID}{c.name}:{i}", nome=c.name,
                                             argumentos=dict(c.args or {})) for i, c in enumerate(chamadas))
            return TurnoIA(pedidos=pedidos, versao_modelo=versao, bruto=content)
        texto = "".join(p.text for p in content.parts if p.text and not p.thought).strip()
        return TurnoIA(resposta=texto or None, versao_modelo=versao, bruto=content)
