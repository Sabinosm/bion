"""Utilitários de consulta compartilhados pelos controllers/repositories:
escape de termos de busca e paginação."""

from flask import request


def escapar_like(termo: str) -> str:
    """Neutraliza \\, % e _ digitados pelo usuário antes de montar um
    padrão LIKE/ILIKE. Usar sempre junto com escape='\\\\' no ilike()."""
    return termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def ler_paginacao(padrao: int = 20, maximo: int = 100) -> tuple[int, int]:
    """Lê ?pagina= e ?por_pagina= da requisição, com limites seguros."""
    try:
        pagina = max(int(request.args.get("pagina", 1)), 1)
    except ValueError:
        pagina = 1
    try:
        por_pagina = int(request.args.get("por_pagina", padrao))
    except ValueError:
        por_pagina = padrao
    return pagina, min(max(por_pagina, 1), maximo)


def resposta_paginada(paginacao, serializar) -> dict:
    """Converte o objeto de paginação do Flask-SQLAlchemy no dict
    devolvido em json_success(data=...)."""
    return {
        "itens": [serializar(i) for i in paginacao.items],
        "pagina": paginacao.page,
        "por_pagina": paginacao.per_page,
        "total": paginacao.total,
        "paginas": paginacao.pages,
    }