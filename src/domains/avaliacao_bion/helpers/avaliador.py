"""Laco da avaliacao: a IA pede metodos da pool, responde, o sistema valida e
devolve os erros se precisar. PURO: sem banco, sem Flask. Quem chama grava o resultado.

Limites (todos finitos): `pool.max_rodadas` rodadas de ferramentas e
`max_tentativas` respostas finais invalidas.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.domains.output_ia import OutputIA, casca, interpretar
from src.domains.pool_ia import Pool
from src.domains.input_ia.nucleo import linhas
from src.domains.protocolos_ia.domain.context.sanitizer import limpar_estrutura

from .cliente import ClienteIA
from .status import IA_INDISPONIVEL, RESPOSTA_INVALIDA
from .prompt import VERSAO_PROMPT, conversa_inicial, feedback_rejeicao, texto

log = logging.getLogger(__name__)

MAX_TENTATIVAS = 3



@dataclass(frozen=True)
class Avaliacao:
    ok: bool
    output: OutputIA | None = None
    erro_codigo: str | None = None
    erros: list[str] = field(default_factory=list)
    versao_modelo: str | None = None


def _versao(cliente: ClienteIA, turno_versao: str | None) -> str:
    return f"{turno_versao or cliente.versao}/p{VERSAO_PROMPT}"[:50]


def _prompt_de_snapshot(snapshot: dict) -> str:
    """Renderiza apenas o contexto clinico congelado e remove identificadores comuns."""
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot clinico invalido")
    contexto = snapshot.get("contexto")
    if not isinstance(contexto, dict) or not contexto:
        raise ValueError("snapshot sem contexto clinico")
    idioma = snapshot.get("idioma_resposta")
    idioma = idioma if isinstance(idioma, str) and idioma.strip() else "pt-BR"
    partes = [f"idioma_resposta: {idioma}"]
    faltando = snapshot.get("faltando", [])
    if not isinstance(faltando, list) or not all(isinstance(x, str) for x in faltando):
        raise ValueError("lista de lacunas do snapshot invalida")
    faltando = limpar_estrutura(faltando)
    if faltando:
        partes.append("## lacunas\n" + "\n".join(f"- {x}" for x in faltando))
    for nome, dados in contexto.items():
        if not isinstance(nome, str) or not nome or not isinstance(dados, dict):
            raise ValueError("bloco do snapshot invalido")
        dados = limpar_estrutura(dados)
        partes.append("\n".join([f"## {nome}", *linhas(dados)]))
    return "\n\n".join(partes)


def avaliar(snapshot: dict, pool: Pool, cliente: ClienteIA, *, max_tentativas: int = MAX_TENTATIVAS) -> Avaliacao:
    nomes = list((snapshot.get("contexto") or {}).keys())
    conversa = conversa_inicial(_prompt_de_snapshot(snapshot))
    ferramentas, esquema = pool.catalogo(), casca()
    rodada = tentativas = 0
    versao = None

    while True:
        pode = rodada < pool.max_rodadas
        try:
            turno = cliente.turno(conversa, ferramentas if pode else [], esquema)
        except Exception:
            log.exception("falha ao chamar o modelo de IA")     # sem conteudo clinico na mensagem
            return Avaliacao(False, erro_codigo=IA_INDISPONIVEL, versao_modelo=_versao(cliente, versao))
        versao = turno.versao_modelo or versao

        if turno.pedidos and pode:
            rodada += 1
            conversa.append({"papel": "ia", "pedidos": [
                {"id": p.id, "nome": p.nome, "argumentos": p.argumentos} for p in turno.pedidos]})
            for p in turno.pedidos:
                conversa.append({"papel": "ferramenta", "pedido_id": p.id, "nome": p.nome,
                                 "conteudo": pool.executar(rodada, p.nome, p.argumentos)})
            continue

        if turno.pedidos:   # pediu ferramenta sem rodadas: conta como resposta invalida
            erros = ["limite de rodadas de consulta atingido"]
            bruto = ""
        else:
            bruto = turno.resposta
            r = interpretar(bruto, nomes, medicamentos_validos=pool.medicamentos_validos(),
                            exames_validos=pool.exames_validos())
            if r.ok:
                return Avaliacao(True, output=r.output, versao_modelo=_versao(cliente, versao))
            erros = r.erros

        tentativas += 1
        if tentativas >= max_tentativas:
            return Avaliacao(False, erro_codigo=RESPOSTA_INVALIDA, erros=erros, versao_modelo=_versao(cliente, versao))
        conversa.append({"papel": "ia", "conteudo": texto(bruto) if bruto not in (None, "") else ""})
        conversa.append(feedback_rejeicao(erros, rodada < pool.max_rodadas))