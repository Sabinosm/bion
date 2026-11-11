"""
Entrypoint de linha de comando para as rotinas de sincronização do
domínio de medicamentos.

Este é o único arquivo do domínio que importa create_app -- os módulos
services/sincronizar_catalogo_service.py e
interacoes/sincronizar_interacoes_service.py são passivos: expõem uma
função executar() e assumem que quem chama já tem app_context aberto.
Isso inverte a dependência (os módulos de sincronização não "passeiam"
importando app) e permite que outro ponto de entrada -- Celery task,
endpoint administrativo, teste -- reutilize as mesmas funções
executar() sem precisar montar sua própria app do zero, só abrindo o
app_context que já tiver.

Cada etapa roda isolada: se uma falha, a falha é logada e a próxima
etapa ainda roda. O código de saída é 1 se qualquer etapa falhar
(útil para cron/monitoramento) e 0 se todas passarem.

Uso:
    python -m src.domains.medicamentos.cli_sincronizacao catalogo
    python -m src.domains.medicamentos.cli_sincronizacao interacoes
    python -m src.domains.medicamentos.cli_sincronizacao todos
"""

import logging
import os
import sys

from seeds.medicamentos import sincronizar_catalogo_service
from seeds.medicamentos import sincronizar_interacoes_service
from dotenv import load_dotenv
from .seed_principio_normalizado import seed as seed_principio_normalizado
load_dotenv()
logger = logging.getLogger(__name__)


def seed(alvo, app):
    alvo = alvo.lower()

    if alvo not in ("catalogo", "interacoes", "todos"):
        print(f"Alvo desconhecido: {alvo!r}. Use: catalogo | interacoes | todos.")
        return 1

    etapas = []
    if alvo in ("catalogo", "todos"):
        etapas.append(("catalogo", sincronizar_catalogo_service.executar))
    if alvo in ("interacoes", "todos"):
        etapas.append(("interacoes", sincronizar_interacoes_service.executar))

    # Mesma variável de ambiente que app.py usa -- sem isso, a
    # sincronização sempre rodaria com config de "development",
    # mesmo quando disparada em produção.
    app = app

    falhas = 0
    with app.app_context():
        for nome, executar in etapas:
            try:
                executar()
            except Exception:
                logger.exception("Falha na sincronização de %s", nome)
                falhas += 1

    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(seed())
    sys.exit(seed_principio_normalizado())