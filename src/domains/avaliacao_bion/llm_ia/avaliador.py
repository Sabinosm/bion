"""avaliador.py

Laço da avaliação clínica por IA: a IA pede ferramentas da pool, responde, o sistema valida a resposta e devolve os erros para nova tentativa. É puro (sem banco e sem Flask): quem chama grava o resultado. Todos os limites são finitos: rodadas de ferramentas da pool e respostas finais inválidas. Cada chamada ao modelo gera um registro de auditoria operacional.
"""
from __future__ import annotations

import logging
from time import perf_counter
from dataclasses import dataclass, field

from src.domains.output_ia import OutputIA, casca, interpretar
from src.domains.pool_ia import Pool
from .auditoria import AuditSink
from .cliente import ClienteIA

from .auditoria_operacional import AuditoriaDaAvaliacao
from .codigos import IA_INDISPONIVEL, RESPOSTA_INVALIDA
from .contexto import ContextoSeguro
from .prompts.prescricao import VERSAO_PROMPT, conversa_inicial, feedback_rejeicao, texto

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


def _ms(inicio: float) -> int:
    return int((perf_counter() - inicio) * 1000)


def _prompt_de_snapshot(snapshot: dict) -> str:
    return ContextoSeguro.de_snapshot(snapshot).para_prompt()


def avaliar(snapshot: dict, pool: Pool, cliente: ClienteIA, *, max_tentativas: int = MAX_TENTATIVAS,
            uuid_output: str | None = None, auditoria: AuditSink | None = None) -> Avaliacao:
    aud = AuditoriaDaAvaliacao(cliente, uuid_output, auditoria)
    contexto = ContextoSeguro.de_snapshot(snapshot)
    nomes = contexto.nomes
    esquema = casca()
    conversa = conversa_inicial(contexto.para_prompt(), esquema)
    ferramentas = pool.catalogo()
    rodada = tentativas = 0
    versao = None

    while True:
        pode = rodada < pool.max_rodadas
        inicio = perf_counter()
        try:
            turno = cliente.turno(conversa, ferramentas if pode else [], esquema)
        except Exception as exc:
            aud.falha(exc, _ms(inicio))
            log.exception("falha ao chamar o modelo de IA")     # sem conteudo clinico na mensagem
            return Avaliacao(False, erro_codigo=IA_INDISPONIVEL, versao_modelo=_versao(cliente, versao))
        versao = turno.versao_modelo or versao
        latencia = _ms(inicio)

        if turno.pedidos and pode:
            aud.turno(turno, latencia)
            rodada += 1
            # bruto: turno original do fornecedor; o Gemini 3+ exige devolve-lo (thought_signature)
            conversa.append({"papel": "ia", "bruto": turno.bruto, "pedidos": [
                {"id": p.id, "nome": p.nome, "argumentos": p.argumentos} for p in turno.pedidos]})
            for p in turno.pedidos:
                conversa.append({"papel": "ferramenta", "pedido_id": p.id, "nome": p.nome,
                                 "conteudo": pool.executar(rodada, p.nome, p.argumentos)})
            continue

        if turno.pedidos:   # pediu ferramenta sem rodadas: conta como resposta invalida
            aud.turno(turno, latencia, resposta_valida=False)
            erros = ["limite de rodadas de consulta atingido"]
            bruto = ""
        else:
            bruto = turno.resposta
            r = interpretar(bruto, nomes, medicamentos_validos=pool.medicamentos_validos(),
                            exames_validos=pool.exames_validos())
            aud.turno(turno, latencia, resposta_valida=r.ok)
            if r.ok:
                return Avaliacao(True, output=r.output, versao_modelo=_versao(cliente, versao))
            erros = r.erros

        tentativas += 1
        if tentativas >= max_tentativas:
            return Avaliacao(False, erro_codigo=RESPOSTA_INVALIDA, erros=erros, versao_modelo=_versao(cliente, versao))
        conversa.append({"papel": "ia", "conteudo": texto(bruto) if bruto not in (None, "") else ""})
        conversa.append(feedback_rejeicao(erros, rodada < pool.max_rodadas))