"""Preenche principio_ativo_normalizado nas linhas já existentes de
catalogo_medicamentos. Rodar UMA vez, depois de adicionar a coluna e
antes de criar o índice único (ver sql/migracao_medicamentos.sql).

Uso (na raiz do projeto):
    python -m scripts.seed_principio_normalizado
"""

import os

from src.main import create_app
from src.models import db
from src.models.catalogos.catalogo_medicamentos import CatalogoMedicamentos
from src.domains.medicamentos.normalizacao import normalizar_nome


def main():
    app = create_app(os.getenv("FLASK_ENV", "development"))
    with app.app_context():
        pendentes = CatalogoMedicamentos.query.filter(
            CatalogoMedicamentos.principio_ativo_normalizado.is_(None)
        ).all()
        for m in pendentes:
            if m.principio_ativo:
                m.principio_ativo_normalizado = normalizar_nome(m.principio_ativo)
        db.session.commit()
        print(f"seed concluído: {len(pendentes)} linhas verificadas.")


if __name__ == "__main__":
    main()
