"""Interface com o modelo de IA. O resto do pacote so conhece isto.

Formato NEUTRO de conversa (um adaptador traduz para o fornecedor escolhido):
    {"papel": "sistema",    "conteudo": str}
    {"papel": "usuario",    "conteudo": str}
    {"papel": "ia",         "conteudo": str}                       # resposta final em texto
    {"papel": "ia",         "pedidos": [{"id","nome","argumentos"}]}
    {"papel": "ferramenta", "pedido_id": str, "nome": str, "conteudo": dict}

Cada chamada a `turno` devolve OU pedidos de ferramenta (metodos da pool) OU a
resposta final (JSON em texto ou dict) que sera validada contra `casca`.
"""
from __future__ import annotations

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


class ClienteIA(Protocol):
    versao: str

    def turno(self, conversa: list[dict], ferramentas: list[dict], casca: dict) -> TurnoIA:
        """`ferramentas` vazia = a IA deve responder agora. Levante excecao se o
        fornecedor falhar (o avaliador registra erro_codigo='ia_indisponivel')."""
        ...


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
