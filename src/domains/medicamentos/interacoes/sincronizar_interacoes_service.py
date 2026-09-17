"""
Rotina de sincronização de INTERAÇÕES medicamentosas com a fonte
externa Detecta Interações (CRF-MG / UFSJ).

Separado de comando_sincronizar_catalogo.py de propósito: fontes,
entidades e formatos diferentes (ver atualizacao_interacoes_service.py
para o raciocínio completo).

Este módulo não monta a aplicação nem cuida de contexto Flask -- ele é
importado e chamado por quem já está dentro de um app_context (CLI
central, Celery task, endpoint administrativo, etc). Não há endpoint
HTTP direto para isso -- é ação do sistema, não de usuário -- mas quem
agenda (cron, Celery beat) é responsabilidade de fora deste arquivo.

Uso (exemplo, a partir de um entrypoint que já tem app_context aberto):
    from src.catalogos.comando_sincronizar_interacoes import executar
    executar()
"""

import os

import requests

from .atualizacao_interacoes_service import AtualizacaoInteracoesService

FONTE = "detecta-interacoes-crfmg"
BASE_URL = "https://imses.crfmg.org.br/api"


def buscar_itens_detecta_interacoes() -> list[dict]:
    """
    Busca todas as interações na API do Detecta Interações via
    GET /medicamentos, que retorna cada medicamento já com suas
    interações embutidas -- evita ter que perguntar par a par.

    Formato real da API (confirmado via /api/openapi.yaml):
    {
      "medicamentos": [
        {
          "id": 0, "nome": "string", "indicacoes": "string",
          "interacoes": [
            {
              "id": 0,
              "medicamento1": {"id", "nome", "indicacoes"},
              "medicamento2": {"id", "nome", "indicacoes"},
              "mecanismo_efeito": "string",
              "recomendacoes": "string",
              "acao": "string"
            }
          ]
        }
      ]
    }

    Requer chave de API (header, ver DETECTA_INTERACOES_API_KEY) --
    401 se ausente/inválida. Formato exato do header não confirmado
    na doc consultada (comum ser "Authorization: Bearer <key>" ou
    "X-API-Key: <key>") -- ajustar após primeiro teste real.

    A API expõe "nome" do medicamento, não "principio_ativo"
    separadamente -- assumimos aqui que o campo nome já é o nome do
    princípio ativo (coerente com a lista vista no site: "Paracetamol",
    "Varfarina" etc, sem marca comercial). Cada interação vem
    duplicada (aparece tanto na lista do medicamento1 quanto do
    medicamento2) -- deduplicamos por id da interação antes de
    devolver, para não processar a mesma interação duas vezes.

    PLACEHOLDER: enquanto DETECTA_INTERACOES_API_KEY não estiver
    configurada (chave ainda não obtida/confirmada com os autores),
    retorna lista vazia em vez de chamar a API ou quebrar com erro --
    permite rodar o comando de ponta a ponta (e testar o resto do
    pipeline: catálogo, service, log) sem a credencial real em mãos.
    Assim que a chave existir, exportar DETECTA_INTERACOES_API_KEY no
    ambiente é suficiente para a integração real passar a rodar, sem
    precisar tocar neste código.
    """
    api_key = os.environ.get("DETECTA_INTERACOES_API_KEY")
    if not api_key:
        print(
            "[AVISO] DETECTA_INTERACOES_API_KEY não configurada -- "
            "pulando sincronização de interações (retornando lista vazia). "
            "Configure a variável de ambiente quando a chave estiver disponível."
        )
        return []

    resposta = requests.get(
        f"{BASE_URL}/medicamentos",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resposta.raise_for_status()
    dados = resposta.json()

    interacoes_por_id = {}
    for medicamento in dados.get("medicamentos", []):
        for interacao in medicamento.get("interacoes", []):
            interacoes_por_id[interacao["id"]] = interacao

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

    return itens


def executar() -> dict | None:
    """Ponto de entrada chamado por quem já tem app_context aberto.
    Retorna o resultado da sincronização, ou None quando roda em modo
    placeholder (chave de API ausente) -- ver
    buscar_itens_detecta_interacoes."""
    itens = buscar_itens_detecta_interacoes()

    if not itens and not os.environ.get("DETECTA_INTERACOES_API_KEY"):
        # Aviso já foi impresso em buscar_itens_detecta_interacoes;
        # aqui só evita seguir chamando o service com lista vazia
        # e imprimindo um resultado que parece uma sincronização
        # real bem-sucedida.
        return None

    service = AtualizacaoInteracoesService()
    resultado = service.sincronizar(itens, FONTE)

    print(f"Fonte: {FONTE}")
    print(f"Criadas: {len(resultado['criadas'])}")
    print(f"Atualizadas: {len(resultado['atualizadas'])}")
    print(f"Ignoradas (sem correspondência no catálogo): "
          f"{len(resultado['ignoradas_sem_catalogo'])}")
    print(f"Inalteradas: {resultado['total_inalteradas']}")

    return resultado