"""Interface com o modelo de IA. O resto do pacote so conhece isto.

Formato NEUTRO de conversa (um adaptador traduz para o fornecedor escolhido):
    {"papel": "sistema",    "conteudo": str}
    {"papel": "usuario",    "conteudo": str}
    {"papel": "ia",         "conteudo": str,  "bruto": ...}        # resposta final em texto
    {"papel": "ia",         "pedidos": [{"id","nome","argumentos"}], "bruto": ...}
    {"papel": "ferramenta", "pedido_id": str, "nome": str, "conteudo": dict}

`bruto` e o estado OPACO do fornecedor para aquele turno (o avaliador so o guarda
e o devolve na conversa). Existe porque alguns fornecedores exigem reenviar o
turno original intacto (ex.: assinaturas de raciocinio do Gemini em chamadas de ferramenta).

Cada chamada a `turno` devolve OU pedidos de ferramenta (metodos da pool) OU a
resposta final (JSON em texto ou dict) que sera validada contra `casca`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class PedidoFerramenta:
    id: str
    nome: str
    argumentos: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TurnoIA:
    pedidos: tuple[PedidoFerramenta, ...] = ()
    resposta: str | dict | None = None
    versao_modelo: str | None = None
    bruto: Any = None   # estado opaco do fornecedor; devolvido na conversa


class ClienteIA(Protocol):
    versao: str

    def turno(self, conversa: list[dict], ferramentas: list[dict], casca: dict) -> TurnoIA:
        """`ferramentas` vazia = a IA deve responder agora. Levante excecao se o
        fornecedor falhar (o avaliador registra erro_codigo='ia_indisponivel')."""
        ...


class ClienteIABase(ABC):
    """Estrategia abstrata: todo fornecedor (Gemini, outro) a implementa. O avaliador
    so conhece esta interface; qual fornecedor entra e decidido pela fabrica."""
    provedor: str = ""

    @property
    @abstractmethod
    def versao(self) -> str:
        """Identifica modelo/fornecedor (vai para OutputBion.versao_modelo_ia)."""

    @abstractmethod
    def turno(self, conversa: list[dict], ferramentas: list[dict], casca: dict) -> TurnoIA: ...


class ErroIA(RuntimeError):
    """Falha do fornecedor (rede, cota, bloqueio, resposta vazia). Vira erro_codigo='ia_indisponivel'."""


class ClienteIAIndisponivel:
    """Padrao enquanto nao ha modelo: toda chamada falha, e a avaliacao termina
    com status='falhou', erro_codigo='ia_indisponivel'."""
    versao = "indisponivel"

    def turno(self, conversa, ferramentas, casca) -> TurnoIA:
        raise RuntimeError("nenhum modelo de IA configurado")


def pede(nome: str, id: str | None = None, **argumentos) -> TurnoIA:
    return TurnoIA(pedidos=(PedidoFerramenta(id or f"p-{nome}", nome, argumentos),))


def responde(resposta: str | dict) -> TurnoIA:
    return TurnoIA(resposta=resposta)


class ClienteIAFalso:
    """Cliente roteirizado para testes e demonstracao: cada item do roteiro e um
    TurnoIA, uma excecao a levantar, ou um callable(conversa) que devolve um dos dois."""
    versao = "falso-1"

    def __init__(self, roteiro: list[Any]):
        self.roteiro = list(roteiro)
        self.chamadas: list[dict] = []

    def turno(self, conversa, ferramentas, casca) -> TurnoIA:
        self.chamadas.append({"mensagens": len(conversa), "ferramentas": [f["name"] for f in ferramentas],
                              "conversa": list(conversa)})
        if not self.roteiro:
            raise RuntimeError("roteiro do cliente falso esgotado")
        item = self.roteiro.pop(0)
        item = item(conversa) if isinstance(item, Callable) else item
        if isinstance(item, BaseException):
            raise item
        return item
