"""
Rotina de sincronização do CATÁLOGO de medicamentos (principio_ativo,
classe, nomes comerciais) com a fonte externa confiável -- hoje,
ANVISA (dados abertos, CSV público, sem autenticação).

Não sincroniza interações medicamentosas -- isso é responsabilidade de
interacoes/sincronizar_interacoes_service.py, que usa uma fonte
diferente (Detecta Interações / CRF-MG) e uma entidade diferente
(InteracoesMedicamentos). Catálogo e interação têm ciclos de
atualização e formatos de origem independentes; misturar as duas no
mesmo comando acopla fontes que não têm relação entre si.

Este módulo não monta a aplicação nem cuida de contexto Flask -- ele é
importado e chamado por quem já está dentro de um app_context (CLI
central, Celery task, endpoint administrativo, etc). Não há endpoint
HTTP direto para isso -- é ação do sistema, não de usuário -- mas quem
agenda (cron, Celery beat) é responsabilidade de fora deste arquivo.

Uso (exemplo, a partir de um entrypoint que já tem app_context aberto):
    from src.domains.medicamentos.services.sincronizar_catalogo_service import executar
    executar()
"""

import csv
import io
import logging
from datetime import date

import requests

from .atualizacao_medicamentos_service import AtualizacaoMedicamentosService
from ..normalizacao import normalizar_nome

logger = logging.getLogger(__name__)

URL_ANVISA = "https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv"

# Nomes de coluna do CSV. NÃO confirmados contra o arquivo real -- se
# algum estiver diferente, buscar_itens_anvisa() para com um erro que
# lista as colunas encontradas; basta ajustar aqui.
COL_PRINCIPIO = "PRINCIPIO_ATIVO"
COL_CLASSE = "CLASSE_TERAPEUTICA"
COL_NOME = "NOME_PRODUTO"
COL_SITUACAO = "SITUACAO_REGISTRO"


def buscar_itens_anvisa() -> tuple[list[dict], str]:
    """
    Baixa o CSV de dados abertos da ANVISA e converte para o formato
    esperado por AtualizacaoMedicamentosService.sincronizar:
    {"principio_ativo": ..., "classe_farmaceutica": ..., "nomes_comerciais": [...]}.

    Pontos de atenção do CSV:
    - Delimitador ";", encoding ANSI/1252 (não UTF-8).
    - Um princípio ativo aparece em várias linhas (uma por produto) --
      agrupamos pelo nome normalizado antes de montar nomes_comerciais.
    - Só entram registros com situação VÁLIDO.
    - Combinações (ex: "A + B") são puladas: normalizar_nome não cobre
      combinações e elas precisam de tratamento próprio.
    """
    resposta = requests.get(URL_ANVISA, timeout=120)
    resposta.raise_for_status()
    texto = resposta.content.decode("cp1252", errors="replace")

    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
    esperadas = {COL_PRINCIPIO, COL_CLASSE, COL_NOME, COL_SITUACAO}
    faltando = esperadas - set(leitor.fieldnames or [])
    if faltando:
        raise ValueError(
            f"Colunas ausentes no CSV da ANVISA: {sorted(faltando)}. "
            f"Colunas encontradas: {leitor.fieldnames}"
        )

    grupos: dict[str, dict] = {}
    combinacoes = 0
    for linha in leitor:
        if normalizar_nome(linha[COL_SITUACAO] or "") != "ativo":
            continue
        bruto = (linha[COL_PRINCIPIO] or "").strip()
        if not bruto:
            continue
        if "+" in bruto or ";" in bruto:
            combinacoes += 1
            continue

        chave = normalizar_nome(bruto)
        grupo = grupos.setdefault(chave, {
            "principio_ativo": bruto,
            "classe_farmaceutica": None,
            "nomes_comerciais": set(),
        })
        classe = (linha[COL_CLASSE] or "").strip()
        if classe and not grupo["classe_farmaceutica"]:
            grupo["classe_farmaceutica"] = classe
        nome = (linha[COL_NOME] or "").strip()
        if nome:
            grupo["nomes_comerciais"].add(nome)

    itens = [
        {**g, "nomes_comerciais": sorted(g["nomes_comerciais"])}
        for g in grupos.values()
    ]
    logger.info("ANVISA: %d princípios ativos; %d linhas de combinação puladas",
                len(itens), combinacoes)
    return itens, f"ANVISA-DADOS-ABERTOS-{date.today().isoformat()}"


def executar() -> dict:
    """Ponto de entrada chamado por quem já tem app_context aberto.
    Retorna o resultado da sincronização (útil para quem chama logar
    ou expor de outra forma, ex: endpoint administrativo de status)."""
    itens, fonte = buscar_itens_anvisa()

    service = AtualizacaoMedicamentosService()
    resultado = service.sincronizar(itens, fonte)

    logger.info("Fonte: %s", fonte)
    logger.info("Criados: %d", len(resultado["criados"]))
    logger.info("Atualizados: %d", len(resultado["atualizados"]))
    logger.info("Inalterados: %d", resultado["total_inalterados"])

    return resultado