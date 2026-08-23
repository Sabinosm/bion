#!/usr/bin/env python3
"""
setup_bion.py

1. Clona os dois repositórios do GitHub.
2. Cria um .env preenchendo o que dá pra preencher automaticamente.
3. Tenta converter o schema MySQL (create_database.sql) para SQLite
   e criar bion.db a partir dele.
4. Se a conversão para SQLite falhar (schema muito "MySQL-específico"),
   gera automaticamente um docker-compose.yml de MariaDB + uma cópia
   do .sql com FOREIGN_KEY_CHECKS desabilitado, para não precisar
   reordenar as tabelas manualmente. Basta rodar `docker compose up -d`.

Uso:
    python setup_bion.py
    python setup_bion.py --dest ./meus_projetos --sql ./create_database.sql
"""

import argparse
import re
import secrets
import shutil
import sqlite3
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
    print(f"$ {' '.join(cmd)}")
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
    - FLASK_ENV        -> development
    - SECRET_KEY        -> gerado aleatoriamente
    - AES_KEY / HMAC_KEY -> gerados aleatoriamente (hex)
    - DB_* de conexão MySQL real ficam em branco: não temos como
      inventar usuário/senha/host reais de um banco que não existe
      ainda. Deixo defaults sensatos para uso local + SQLite.
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

    lines = []
    for key in ENV_TEMPLATE_KEYS:
        lines.append(f"{key}={values[key]}")

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


# --- conversão bem simples de MySQL DDL -> SQLite -------------------------

TYPE_MAP = [
    (re.compile(r"\bbigint\(\d+\)", re.I), "INTEGER"),
    (re.compile(r"\btinyint\(\d+\)", re.I), "INTEGER"),
    (re.compile(r"\bsmallint\(\d+\)", re.I), "INTEGER"),
    (re.compile(r"\bint\(\d+\)", re.I), "INTEGER"),
    (re.compile(r"\bchar\(\d+\)", re.I), "TEXT"),
    (re.compile(r"\bvarchar\(\d+\)", re.I), "TEXT"),
    (re.compile(r"\blongtext(\s+CHARACTER SET[^,]+?COLLATE\s+\S+)?", re.I), "TEXT"),
    (re.compile(r"\btext\b", re.I), "TEXT"),
    (re.compile(r"\btimestamp\b", re.I), "TEXT"),
    (re.compile(r"\bdatetime(\(\d+\))?\b", re.I), "TEXT"),
    (re.compile(r"\bdate\b", re.I), "TEXT"),
    (re.compile(r"\bdecimal\(\d+,\d+\)", re.I), "REAL"),
]


def convert_mysql_to_sqlite(sql_text: str) -> str:
    """
    Conversão best-effort. NÃO é um conversor completo de MySQL->SQLite:
    - remove CREATE DATABASE
    - remove ENGINE=/DEFAULT CHARSET=/COLLATE= no fim das tabelas
    - remove ENUM(...) -> TEXT
    - remove CHECK(json_valid(...))
    - remove `current_timestamp()` -> CURRENT_TIMESTAMP
    - mapeia tipos numéricos/string básicos
    - remove backticks (SQLite aceita, mas troco por aspas duplas por clareza)
    Pode falhar em construções mais exóticas: se falhar, o script avisa
    e mantém o .sql original intacto para uso em MySQL.
    """
    text = sql_text

    # remove CREATE DATABASE ... ;
    text = re.sub(r"CREATE DATABASE[^;]+;\s*", "", text, flags=re.I)

    # ENUM(...) -> TEXT
    text = re.sub(r"enum\([^)]*\)", "TEXT", text, flags=re.I)

    # CHECK (json_valid(`col`)) -> remove
    text = re.sub(r"\s*CHECK\s*\(json_valid\([^)]*\)\)", "", text, flags=re.I)

    # current_timestamp(6) / current_timestamp() -> CURRENT_TIMESTAMP
    text = re.sub(r"current_timestamp\(\d*\)", "CURRENT_TIMESTAMP", text, flags=re.I)

    # tipos
    for pattern, repl in TYPE_MAP:
        text = pattern.sub(repl, text)

    # AUTO_INCREMENT -> AUTOINCREMENT (só funciona junto de INTEGER PRIMARY KEY,
    # então tratamos de forma simplificada removendo e confiando no PRIMARY KEY)
    text = re.sub(r"\s+AUTO_INCREMENT\b", "", text, flags=re.I)

    # remove ENGINE=... DEFAULT CHARSET=... COLLATE=... AUTO_INCREMENT=N ; no fechamento de tabela
    text = re.sub(
        r"\)\s*ENGINE=\w+[^;]*;",
        ");",
        text,
        flags=re.I,
    )

    # remove backticks
    text = text.replace("`", '"')

    # remove CHARACTER SET / COLLATE soltos que sobraram em colunas
    text = re.sub(r"CHARACTER SET \w+", "", text, flags=re.I)
    text = re.sub(r"COLLATE \w+", "", text, flags=re.I)

    return text


def try_build_sqlite(sql_path: Path, dest_db: Path) -> bool:
    if not sql_path.exists():
        print(f"[aviso] {sql_path} não encontrado — pulando criação do SQLite.")
        return False

    original = sql_path.read_text(encoding="utf-8")
    converted = convert_mysql_to_sqlite(original)

    if dest_db.exists():
        backup = dest_db.with_suffix(".db.bak")
        shutil.copy(dest_db, backup)
        print(f"[aviso] {dest_db} já existia, backup em {backup}")
        dest_db.unlink()

    conn = sqlite3.connect(dest_db)
    cur = conn.cursor()
    try:
        cur.executescript(converted)
        conn.commit()
        print(f"[ok] Banco SQLite criado em {dest_db}")
        return True
    except sqlite3.Error as e:
        conn.close()
        dest_db.unlink(missing_ok=True)
        print("[ERRO] Não consegui converter/criar o SQLite automaticamente.")
        print(f"       Motivo: {e}")
        print(
            "       O schema usa recursos bem específicos de MySQL "
            "(FKs cruzadas com ordem de criação, JSON CHECK, ENUM, etc.) "
            "que a conversão simples não cobre 100%.\n"
            "       O arquivo .sql original continua intacto — "
            "rode-o direto num MySQL/MariaDB, ou ajuste manualmente "
            "as partes que falharem."
        )
        return False
    finally:
        conn.close()


def prepare_mariadb_fallback(sql_path: Path, dest: Path, env_values: dict):
    """
    Não reordena as tabelas manualmente (o schema tem dependências
    cruzadas demais pra isso valer a pena). Em vez disso:
    - copia o .sql envolvendo o conteúdo em
      SET FOREIGN_KEY_CHECKS=0; ... SET FOREIGN_KEY_CHECKS=1;
      que faz o MySQL/MariaDB ignorar a ordem de criação das FKs.
    - gera um docker-compose.yml já configurado com as credenciais
      do .env e que importa esse .sql automaticamente na primeira
      subida do container (via /docker-entrypoint-initdb.d).
    """
    if not sql_path.exists():
        print(f"[aviso] {sql_path} não encontrado — pulando fallback MariaDB.")
        return

    original = sql_path.read_text(encoding="utf-8")
    original = original.replace("bion_testes", env_values["DB_NAME"])
    wrapped = (
        "SET FOREIGN_KEY_CHECKS=0;\n\n"
        + original
        + "\n\nSET FOREIGN_KEY_CHECKS=1;\n"
    )

    initdb_dir = dest / "mariadb-init"
    initdb_dir.mkdir(exist_ok=True)
    sql_out = initdb_dir / "setup_maria_db.sql"
    sql_out.write_text(wrapped, encoding="utf-8")
    print(f"[ok] SQL preparado para MariaDB em {sql_out}")
    print("     (envolvido com SET FOREIGN_KEY_CHECKS=0/1 — não precisa reordenar tabelas)")

    compose_path = dest / "docker-compose.yml"
    compose_content = f"""services:
  mariadb:
    image: mariadb:11
    container_name: teste_mariadb
    restart: unless-stopped
    environment:
      MARIADB_ROOT_PASSWORD: {env_values['DB_PASSWORD'] or 'changeme'}
      MARIADB_DATABASE: {env_values['DB_NAME']}
    ports:
      - "{env_values['DB_PORT']}:3306"
    volumes:
      - ./mariadb-init:/docker-entrypoint-initdb.d
      - teste_mariadb_data:/var/lib/mysql

volumes:
  teste_mariadb_data:
"""
    compose_path.write_text(compose_content, encoding="utf-8")
    print(f"[ok] docker-compose.yml criado em {compose_path}")
    print(
        "     -> rode: docker compose up -d\n"
        "     Na primeira subida, o MariaDB importa automaticamente o .sql\n"
        "     (arquivos em mariadb-init/ só rodam quando o volume de dados\n"
        "     é criado pela primeira vez; se já existir volume, apague-o\n"
        "     ou rode `docker compose down -v` antes de tentar de novo)."
    )
    print(
        f"     Atenção: como DB_PASSWORD ficou vazio no .env, usei 'changeme'\n"
        f"     como senha root do MariaDB — ajuste o .env e o compose para\n"
        f"     algo real antes de usar fora de teste local."
    )


def setup_venv(dest: Path):
    """
    Cria um .venv dentro da pasta do repo `bion` (é o único dos dois
    repos que tem requirements.txt — sabinosm.github.io é um site
    estático) e instala as dependências nele.
    """
    teste_dir = dest / "bion"
    req_file = teste_dir / "requirements.txt"

    if not teste_dir.exists():
        print("[aviso] pasta bion/ não encontrada — pulando criação do .venv.")
        return
    if not req_file.exists():
        print(f"[aviso] {req_file} não encontrado — pulando instalação de dependências.")
        return

    venv_dir = teste_dir / ".venv"
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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

    if not args.no_venv:
        print("\n== Criando .venv e instalando dependências ==")
        setup_venv(dest)
    else:
        print("\n== Pulando .venv (--no-venv) ==")

    if args.sql:
        sql_path = Path(args.sql).resolve()
    else:
        sql_path = dest / "bion" / "database" / "create_database.sql"

    print("\n== Gerando .env ==")
    _, env_values = build_env(dest)

    print("\n== Tentando montar banco SQLite a partir do schema ==")
    db_path = dest / "teste.db"
    ok = try_build_sqlite(sql_path, db_path)

    if not ok:
        print("\n== Preparando alternativa: MariaDB via Docker ==")
        prepare_mariadb_fallback(sql_path, dest, env_values)

    print("\nConcluído.")


if __name__ == "__main__":
    main()