#!/usr/bin/env python3
"""
setup_bion.py

1. Clona os dois repositorios do GitHub.
2. Cria um .env com valores padrao/gerados.
3. Cria um .venv dentro de bion/ e instala requirements.txt.
4. Copia o create_database.sql para a raiz do projeto, pronto para
   voce importar manualmente no seu MySQL/MariaDB.

Uso:
    python setup_bion.py
    python setup_bion.py --dest ./meus_projetos
    python setup_bion.py --no-venv
"""

import argparse
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

REPOS = [
    "https://github.com/Sabinosm/bion.git",
    "https://github.com/Sabinosm/sabinosm.github.io.git",
]

ENV_TEMPLATE_KEYS = [
    "FLASK_ENV",
    "SECRET_KEY",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "AES_KEY",
    "HMAC_KEY",
]


def run(cmd, **kwargs):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def clone_repos(dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    for url in REPOS:
        name = url.rstrip("/").split("/")[-1].removesuffix(".git")
        target = dest / name
        if target.exists():
            print(f"[skip] {target} já existe, não vou clonar de novo.")
            continue
        try:
            run(["git", "clone", url, str(target)])
        except FileNotFoundError:
            print("ERRO: git não encontrado no PATH. Instale o git e rode de novo.")
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(f"ERRO ao clonar {url}: {e}")
            print("(repositório pode ser privado — confira suas credenciais/SSH key)")


def build_env(dest: Path):
    """
    Preenche o que dá pra preencher com segurança/sensatez:
    - FLASK_ENV          -> development
    - SECRET_KEY/AES_KEY/HMAC_KEY -> gerados aleatoriamente (hex)
    - DB_* de conexão MySQL real ficam com defaults sensatos para
      uso local (root/sem senha/localhost:3306/testes) — ajuste
      manualmente se for apontar para um banco real.
    """
    values = {
        "FLASK_ENV": "development",
        "SECRET_KEY": secrets.token_hex(32),
        "DB_USER": "root",
        "DB_PASSWORD": "",
        "DB_HOST": "localhost",
        "DB_PORT": "3306",
        "DB_NAME": "testes",
        "AES_KEY": secrets.token_hex(32),   # 256 bits
        "HMAC_KEY": secrets.token_hex(32),  # 256 bits
    }

    lines = [f"{key}={values[key]}" for key in ENV_TEMPLATE_KEYS]

    env_path = dest / ".env"
    if env_path.exists():
        backup = env_path.with_suffix(".env.bak")
        shutil.copy(env_path, backup)
        print(f"[aviso] .env já existia, backup salvo em {backup}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[ok] .env criado em {env_path}")
    print(
        "     -> DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME são placeholders "
        "para MySQL local (root/sem senha/localhost:3306/testes).\n"
        "     Ajuste manualmente se você for apontar para um banco MySQL real."
    )
    return env_path, values


def setup_venv(dest: Path):
    """
    Cria um .venv dentro da pasta do repo `bion` (é o único dos dois
    repos que tem requirements.txt) e instala as dependências nele.
    """
    bion_dir = dest / "bion"
    req_file = bion_dir / "requirements.txt"

    if not bion_dir.exists():
        print("[aviso] pasta bion/ não encontrada — pulando criação do .venv.")
        return
    if not req_file.exists():
        print(f"[aviso] {req_file} não encontrado — pulando instalação de dependências.")
        return

    venv_dir = bion_dir / ".venv"
    if venv_dir.exists():
        print(f"[skip] {venv_dir} já existe, não vou recriar.")
    else:
        try:
            run([sys.executable, "-m", "venv", str(venv_dir)])
        except subprocess.CalledProcessError as e:
            print(f"[ERRO] Falha ao criar o .venv: {e}")
            return

    pip_path = venv_dir / ("Scripts/pip.exe" if sys.platform == "win32" else "bin/pip")
    try:
        run([str(pip_path), "install", "--upgrade", "pip"])
        run([str(pip_path), "install", "-r", str(req_file)])
        print(f"[ok] .venv criado e dependências instaladas em {venv_dir}")
        activate_hint = (
            f"{venv_dir}\\Scripts\\activate"
            if sys.platform == "win32"
            else f"source {venv_dir}/bin/activate"
        )
        print(f"     -> para ativar: {activate_hint}")
    except subprocess.CalledProcessError as e:
        print(f"[ERRO] Falha ao instalar dependências no .venv: {e}")
        print("       O .venv foi criado, mas você vai precisar rodar o pip install manualmente.")


def copy_sql(dest: Path, sql_arg: str | None):
    """
    Localiza o create_database.sql (dentro do repo clonado, ou no
    caminho informado via --sql) e copia para a raiz do projeto,
    pronto para importação manual no MySQL/MariaDB.
    """
    sql_path = Path(sql_arg).resolve() if sql_arg else dest / "bion" / "database" / "create_database.sql"

    if not sql_path.exists():
        print(f"[aviso] Não encontrei {sql_path}")
        print("        Confira se o repositório bion foi clonado corretamente")
        print("        ou informe o caminho certo com --sql.")
        return

    sql_dest = dest / "create_database.sql"
    shutil.copy(sql_path, sql_dest)
    print(f"[ok] Schema copiado para {sql_dest}")
    print("     -> Importe manualmente no seu MySQL/MariaDB, por exemplo:")
    print(f"        mysql -u root -p < {sql_dest}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dest", default=".", help="Pasta onde clonar os repositórios e criar o .env"
    )
    parser.add_argument(
        "--sql",
        default=None,
        help=(
            "Caminho para o arquivo .sql do schema. Se não for informado, "
            "usa bion/database/create_database.sql dentro do repo clonado."
        ),
    )
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="Não criar .venv nem instalar dependências Python",
    )
    args = parser.parse_args()

    dest = Path(args.dest).resolve()

    print(f"== Clonando repositórios em {dest} ==")
    clone_repos(dest)

    print("\n== Gerando .env ==")
    build_env(dest)

    if not args.no_venv:
        print("\n== Criando .venv e instalando dependências ==")
        setup_venv(dest)
    else:
        print("\n== Pulando .venv (--no-venv) ==")

    print("\n== Preparando o schema SQL ==")
    copy_sql(dest, args.sql)

    print("\nConcluído.")


if __name__ == "__main__":
    main()