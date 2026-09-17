"""
Rotina de sincronização do CATÁLOGO de medicamentos (principio_ativo,
classe, nomes comerciais) com a fonte externa confiável -- hoje,
ANVISA (dados abertos, CSV mensal).

Não sincroniza interações medicamentosas -- isso é responsabilidade de
sincronizar_interacoes.py, que usa uma fonte diferente
(Detecta Interações / CRF-MG) e uma entidade diferente
(InteracoesMedicamentos). Catálogo e interação têm ciclos de
atualização e formatos de origem independentes; misturar as duas no
mesmo comando acopla fontes que não têm relação entre si.

Este módulo não monta a aplicação nem cuida de contexto Flask -- ele é
importado e chamado por quem já está dentro de um app_context (CLI
central, Celery task, endpoint administrativo, etc). Não há endpoint
HTTP direto para isso -- é ação do sistema, não de usuário -- mas quem
agenda (cron, Celery beat) é responsabilidade de fora deste arquivo.

Uso (exemplo, a partir de um entrypoint que já tem app_context aberto):
    from src.catalogos.sincronizar_catalogo_service import executar
    executar()
"""

from .atualizacao_medicamentos_service import AtualizacaoMedicamentosService


def buscar_itens_anvisa() -> tuple[list[dict], str]:
    """
    Busca e faz o parsing do CSV de dados abertos da ANVISA
    (https://dados.anvisa.gov.br/dados/), convertendo cada linha para
    o formato esperado por AtualizacaoMedicamentosService.sincronizar:
    {"principio_ativo": ..., "classe_farmaceutica": ..., "nomes_comerciais": [...]}.

    Pontos de atenção conhecidos do CSV (ver documentação oficial):
    - Delimitador ";", encoding ANSI/1252 (não UTF-8).
    - Um princípio ativo aparece em várias linhas (uma por Nome
      Produto/fabricante) -- é preciso agrupar por princípio ativo
      antes de montar nomes_comerciais.
    - Atualização mensal -- rodar este comando com frequência maior
      que isso não traz dado novo.

    Ainda não implementado -- placeholder até definir se o download é
    automático (requests direto na URL do CSV) ou manual (arquivo
    baixado e lido do disco).
    """
    raise NotImplementedError(
        "Parsing do CSV da ANVISA ainda não implementado."
    )


def executar() -> dict:
    """Ponto de entrada chamado por quem já tem app_context aberto.
    Retorna o resultado da sincronização (útil para quem chama logar
    ou expor de outra forma, ex: endpoint administrativo de status)."""
    itens, fonte = buscar_itens_anvisa()

    service = AtualizacaoMedicamentosService()
    resultado = service.sincronizar(itens, fonte)

    print(f"Fonte: {fonte}")
    print(f"Criados: {len(resultado['criados'])}")
    print(f"Atualizados: {len(resultado['atualizados'])}")
    print(f"Inalterados: {resultado['total_inalterados']}")

    return resultado