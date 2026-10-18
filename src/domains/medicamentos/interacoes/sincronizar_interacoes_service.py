"""
Rotina de sincronização de INTERAÇÕES medicamentosas com a fonte
externa Detecta Interações (CRF-MG / UFSJ).

Separado de services/sincronizar_catalogo_service.py de propósito:
fontes, entidades e formatos diferentes (ver
atualizacao_interacoes_service.py para o raciocínio completo).

Este módulo não monta a aplicação nem cuida de contexto Flask -- ele é
importado e chamado por quem já está dentro de um app_context (CLI
central, Celery task, endpoint administrativo, etc). Não há endpoint
HTTP direto para isso -- é ação do sistema, não de usuário -- mas quem
agenda (cron, Celery beat) é responsabilidade de fora deste arquivo.

Uso (exemplo, a partir de um entrypoint que já tem app_context aberto):
    from src.domains.medicamentos.interacoes.sincronizar_interacoes_service import executar
    executar()
"""

import logging
import os
import time
from collections import Counter
from urllib.parse import quote
from ..normalizacao import normalizar_nome
import requests

from src.models.catalogos.catalogo_medicamentos import CatalogoMedicamentos
from .atualizacao_interacoes_service import AtualizacaoInteracoesService
from ..repository import CatalogoMedicamentosRepository

logger = logging.getLogger(__name__)

FONTE = "detecta-interacoes-crfmg"
BASE_URL = "https://imses.crfmg.org.br/api"

PAUSA_ENTRE_CHAMADAS = 0.2  # segundos; aumentar se a API devolver 429


def _baixar_medicamento(api_key: str, nome: str, contagem: Counter,
                        tentativas: int = 4) -> dict | None:
    """Baixa um medicamento (com interações embutidas) por nome via
    GET /medicamento/{nome}.

    Por que por nome e não GET /medicamentos: a lista completa
    (~375 KB) chega truncada de forma consistente (IncompleteRead),
    mesmo com retry. A resposta por nome é pequena e não sofre isso.

    Cada resposta HTTP é registrada em `contagem` pelo código de status
    (ex: "200", "400", "404", "401"). Falhas de rede repetidas são
    registradas em "retry_rede" (a cada nova tentativa) e "falha_rede"
    (quando esgota as tentativas).

    Retorna None quando o Detecta responde 400 ou 404 para o nome --
    tratado como "sem dados" e a rotina segue. Outros erros HTTP (401,
    403, 429, 500) sobem de propósito, pois indicam problema geral.
    """
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = requests.get(
                f"{BASE_URL}/medicamento/{quote(nome, safe='')}",
                headers={"X-API-Key": api_key, "accept": "application/json"},
                timeout=(10, 60),
            )
            contagem[str(resposta.status_code)] += 1

            if resposta.status_code in (400, 404):
                logger.warning(
                    "Detecta: %s ignorado (HTTP %d): %s",
                    nome, resposta.status_code, resposta.text[:200],
                )
                return None
            resposta.raise_for_status()
            return resposta.json()
        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            ultimo_erro = e
            contagem["retry_rede"] += 1
            espera = 2 ** tentativa
            logger.warning(
                "Detecta: falha de rede em %s (tentativa %d/%d): %s. "
                "Nova tentativa em %ds.",
                nome, tentativa, tentativas, e, espera,
            )
            time.sleep(espera)
    contagem["falha_rede"] += 1
    raise ultimo_erro


def _imprimir_resumo(contagem: Counter, total_nomes: int, com_interacoes: int):
    """Imprime (print) um resumo da consulta ao Detecta, pronto para
    copiar para um TXT. Mostra quantos nomes do catálogo foram
    consultados, quantos deram cada status e quantos ficaram sem
    consultar (quando a rotina aborta no meio)."""
    respostas_http = sum(v for k, v in contagem.items() if k.isdigit())
    nao_consultados = max(total_nomes - respostas_http - contagem["falha_rede"], 0)

    linhas = [
        "",
        "=" * 50,
        "RESUMO DA CONSULTA AO DETECTA INTERACOES",
        "=" * 50,
        f"Nomes no catalogo ............ {total_nomes}",
        f"Nao consultados (abortou) .... {nao_consultados}",
        f"Com interacoes (200 c/ dados)  {com_interacoes}",
        "-" * 50,
        "Respostas por status HTTP:",
    ]
    status_http = sorted(k for k in contagem if k.isdigit())
    if status_http:
        for status in status_http:
            linhas.append(f"  HTTP {status} ................ {contagem[status]}")
    else:
        linhas.append("  (nenhuma resposta recebida)")
    linhas += [
        "-" * 50,
        f"Retries por falha de rede .... {contagem['retry_rede']}",
        f"Falhas de rede definitivas ... {contagem['falha_rede']}",
        "=" * 50,
        "",
    ]
    print("\n".join(linhas))


def buscar_itens_detecta_interacoes() -> list[dict]:
    """
    Busca as interações na API do Detecta Interações, consultando um
    medicamento por vez (GET /medicamento/{nome}) a partir dos
    princípios ativos do catálogo local.

    Formato da resposta por nome (confirmado no Swagger):
    {
      "medicamento": {"id", "nome", "indicacoes"},
      "interacoes": [
        {
          "id": 0,
          "medicamento1": {"id", "nome", "indicacoes"},
          "medicamento2": {"id", "nome", "indicacoes"},
          "mecanismo_efeito": "string",
          "recomendacoes": "string",
          "acao": "string"   # ex: "Evitar a associação", "Monitorizar de perto"
        }
      ]
    }

    Autenticação: header X-API-Key (confirmado pelo Swagger), com a
    chave em DETECTA_INTERACOES_API_KEY.

    Cada interação aparece na resposta dos dois medicamentos
    envolvidos -- deduplicamos por id da interação antes de devolver.

    Ao final (mesmo se abortar), imprime um resumo com a contagem de
    respostas por status -- ver _imprimir_resumo.

    PLACEHOLDER: se DETECTA_INTERACOES_API_KEY não estiver
    configurada, retorna lista vazia em vez de chamar a API.

    Requer app_context aberto (consulta o catálogo).
    """
    api_key = os.environ.get("DETECTA_INTERACOES_API_KEY")
    if not api_key:
        logger.warning(
            "DETECTA_INTERACOES_API_KEY não configurada -- pulando "
            "sincronização de interações (retornando lista vazia). "
            "Configure a variável de ambiente quando a chave estiver disponível."
        )
        return []

    interacoes_por_id = {}
    contagem: Counter = Counter()
    com_interacoes = 0
    nomes = [m.principio_ativo for m in CatalogoMedicamentos.query.all()
             if m.principio_ativo]

    try:
        for i, nome in enumerate(nomes, 1):
            medicamento = medicamento = _baixar_medicamento(api_key, normalizar_nome(nome).capitalize(), contagem)
            if medicamento:
                lista = medicamento.get("interacoes", [])
                if lista:
                    com_interacoes += 1
                for interacao in lista:
                    interacoes_por_id[interacao["id"]] = interacao
            if i % 100 == 0:
                logger.info("Detecta: %d/%d medicamentos consultados", i, len(nomes))
            time.sleep(PAUSA_ENTRE_CHAMADAS)
    finally:
        _imprimir_resumo(contagem, len(nomes), com_interacoes)

    itens = []
    for interacao in interacoes_por_id.values():
        itens.append({
            "principio_ativo_a": interacao["medicamento1"]["nome"],
            "principio_ativo_b": interacao["medicamento2"]["nome"],
            "gravidade": None,  # API não expõe gravidade -- decisão: fica NULL
            "mecanismo_efeito": interacao.get("mecanismo_efeito"),
            "recomendacao": interacao.get("recomendacoes"),
            "acao": interacao.get("acao"),
        })

    logger.info("Detecta: %d interações únicas coletadas", len(itens))
    return itens


def executar() -> dict | None:
    """Ponto de entrada chamado por quem já tem app_context aberto.
    Retorna o resultado da sincronização, ou None quando roda em modo
    placeholder (chave de API ausente) -- ver
    buscar_itens_detecta_interacoes."""
    itens = buscar_itens_detecta_interacoes()

    if not itens and not os.environ.get("DETECTA_INTERACOES_API_KEY"):
        # Aviso já foi emitido em buscar_itens_detecta_interacoes; aqui
        # só evita seguir chamando o service com lista vazia e logando
        # um resultado que parece uma sincronização real bem-sucedida.
        return None

    service = AtualizacaoInteracoesService()
    resultado = service.sincronizar(itens, FONTE)
    repo = CatalogoMedicamentosRepository()
    sem_catalogo = set()
    for par in resultado["ignoradas_sem_catalogo"]:
        for nome in (par["principio_ativo_a"], par["principio_ativo_b"]):
            if not repo.find_por_nome_normalizado(nome):
                sem_catalogo.add(nome)
    print("\nNomes do Detecta sem correspondência no catálogo "
          f"({len(sem_catalogo)}):")
    for nome in sorted(sem_catalogo):
        print(f"  - {nome}")
    logger.info("Fonte: %s", FONTE)
    logger.info("Criadas: %d", len(resultado["criadas"]))
    logger.info("Atualizadas: %d", len(resultado["atualizadas"]))
    logger.info("Ignoradas (sem correspondência no catálogo): %d",
                len(resultado["ignoradas_sem_catalogo"]))
    logger.info("Inalteradas: %d", resultado["total_inalteradas"])

    return resultado