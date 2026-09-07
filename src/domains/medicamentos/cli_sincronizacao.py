"""
Entrypoint de linha de comando para as rotinas de sincronização do
domínio de medicamentos.

Este é o único arquivo do domínio que importa criar_app -- os módulos
comando_sincronizar_catalogo.py e comando_sincronizar_interacoes.py
são passivos: expõem uma função executar() e assumem que quem chama já
tem app_context aberto. Isso inverte a dependência (os comandos não
"passeiam" importando app) e permite que outro ponto de entrada --
Celery task, endpoint administrativo, teste -- reutilize as mesmas
funções executar() sem precisar montar sua própria app do zero, só
abrindo o app_context que já tiver.

Uso:
    python -m src.catalogos.cli_sincronizacao catalogo
    python -m src.catalogos.cli_sincronizacao interacoes
    python -m src.catalogos.cli_sincronizacao todos
"""

import os
import sys

from src.main import create_app
from src.domains.medicamentos import sincronizar_catalogo_service
from src.domains.medicamentos import sincronizar_interacoes_service


def main():
    alvo = sys.argv[1] if len(sys.argv) > 1 else "todos"

    if alvo not in ("catalogo", "interacoes", "todos"):
        print(f"Alvo desconhecido: {alvo!r}. Use: catalogo | interacoes | todos.")
        return 1

    # Mesma variável de ambiente que app.py usa -- sem isso, a
    # sincronização sempre rodaria com config de "development",
    # mesmo quando disparada em produção.
    
    app = create_app(os.getenv("FLASK_ENV", "development"))
    with app.app_context():
        if alvo in ("catalogo", "todos"):
            sincronizar_catalogo_service.executar()
        if alvo in ("interacoes", "todos"):
            sincronizar_interacoes_service.executar()

    return 0


if __name__ == "__main__":
    sys.exit(main())