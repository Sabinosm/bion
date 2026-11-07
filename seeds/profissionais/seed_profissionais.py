"""seed_profissionais.py -- Popula profissionais de teste a partir de CSV.

Uso (CLI):
    python -m src.seeds.seed_profissionais --empresa 1
    python -m src.seeds.seed_profissionais --empresa 1 --dry-run   # valida sem commitar
    python -m src.seeds.seed_profissionais --empresa 1 --ate 20    # só as 20 primeiras linhas

Uso (código):
    from src.seeds.seed_profissionais import seed_profissionais
    resultado = seed_profissionais(empresa=1, dry_run=True, app=app)
    if not resultado["ok"]:
        for e in resultado["erros"]:
            print(e["linha"], e["profissional"], e["erro"])

Como funciona:
  1. Lê seed_profissionais.csv (uma linha por profissional).
  2. Cada linha roda dentro de um SAVEPOINT: se uma linha falha, só ela é
     desfeita e o erro é registrado; as demais continuam. Assim você recebe
     TODOS os erros de uma vez, não só o primeiro.
  3. Se houve qualquer erro (ou --dry-run) -> rollback total. Senão -> um
     único commit no final (tudo atômico, ou nada).

O que cada linha cria:
  - 1 Usuario (status/flags conforme CSV; is_super_admin NUNCA é setado).
  - 1 PapelProfissional ativo ('medico' -> CRM/RQE; 'enfermeiro' -> COREN +
    especialidade).
  - cpf cifrado com AES (coluna 'cpf') + HMAC-SHA256 (coluna 'cpf_hash'),
    usando os MESMOS helpers do runtime -- sem isso, find_by_cpf_hash
    nunca acha esses usuários.
  - hash_senha: SENHA_PADRAO_SEED (default 'Mudar@123') já hasheada, para
    admins conseguirem logar (senha_versao=1). Ajuste o helper de hash se
    o projeto usar outro.

Dedupe: linha cujo cpf_hash / user_login / email já exista no banco é
registrada como erro (constraint unique iria explodir no commit final).
"""

import argparse
import contextlib
import csv
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models import db
from src.models.usuarios import Usuario, PapelProfissional
from src.domains.usuario.repository import UsuarioRepository
# CPF é cifrado (AES-256-GCM) e tem hash HMAC -- o seed precisa usar os
# MESMOS helpers do runtime. Ajuste os nomes se divergirem dos reais.
from src.core.security import aes_encrypt, hmac_sha256

CSV_PADRAO = Path(__file__).with_name("seed_profissionais.csv")

from src.core.security import ph

SENHA_PADRAO_SEED = os.environ.get("SENHA_PADRAO_SEED", "Mudar@123")

TIPOS_PAPEL = {"medico", "enfermeiro"}
STATUS_VALIDOS = {"ativo", "inativo", "pendente"}
COLUNAS_OBRIGATORIAS = {
    "nome_completo", "cpf", "email", "user_login", "tipo_papel", "is_admin",
    "status", "numero_crm", "uf_crm", "rqe", "numero_coren", "uf_coren",
    "especialidade",
}
REGEX_UF = re.compile(r"^[A-Z]{2}$")


# ----------------------------------------------------------------------------
# Conversores
# ----------------------------------------------------------------------------
def _d(v: str):
    return v or None


def _bool(v: str):
    return (v or "").strip().lower() in ("1", "true", "t", "sim")


def _i(v: str):
    return int(v) if v else None


# ----------------------------------------------------------------------------
# Montagem dos models (espelha as colunas de Usuario / PapelProfissional)
# ----------------------------------------------------------------------------
def _montar_usuario(row: dict, id_empresa: int, hash_pronto: str) -> Usuario:
    cpf = re.sub(r"\D", "", row["cpf"])
    return Usuario(
        id_empresa=id_empresa,
        nome_completo=row["nome_completo"].strip(),
        cpf=aes_encrypt(cpf),          # coluna cifrada (String 500)
        cpf_hash=hmac_sha256(cpf),     # índice determinístico NOT NULL
        email=row["email"].strip().lower(),
        telefone=_d(row["telefone"]),
        user_login=row["user_login"].strip().lower(),
        is_admin=_bool(row["is_admin"]),
        is_super_admin=False,          # seed NUNCA cria super admin
        status=row["status"].strip(),
        hash_senha=hash_pronto,
        senha_versao=1,
        onboarding_pendente=False,
    )


def _montar_papel(row: dict, usuario: Usuario) -> PapelProfissional:
    if row["tipo_papel"] == "medico":
        return PapelProfissional(
            usuario=usuario,
            tipo_papel="medico",
            numero_conselho=row["numero_crm"],
            uf_conselho=row["uf_crm"],
            especialidade=_d(row["especialidade"]),
            rqe=_d(row["rqe"]),
            ativo=True,
        )
    return PapelProfissional(
        usuario=usuario,
        tipo_papel="enfermeiro",
        numero_conselho=row["numero_coren"],
        uf_conselho=row["uf_coren"],
        especialidade=_d(row["especialidade"]),
        rqe=None,
        ativo=True,
    )


# ----------------------------------------------------------------------------
# Validação amigável (antes de tocar no banco)
# ----------------------------------------------------------------------------
def _validar_linha(row: dict, repo: UsuarioRepository) -> list:
    problemas = []
    tipo = (row.get("tipo_papel") or "").strip()
    status = (row.get("status") or "").strip()

    if tipo not in TIPOS_PAPEL:
        problemas.append(f"tipo_papel inválido: {tipo!r} (esperado medico/enfermeiro)")
    if status not in STATUS_VALIDOS:
        problemas.append(f"status inválido: {status!r} (esperado ativo/inativo/pendente)")
    if not (row.get("nome_completo") or "").strip():
        problemas.append("nome_completo vazio (NOT NULL)")
    if not (row.get("email") or "").strip():
        problemas.append("email vazio (unique NOT NULL)")
    if not (row.get("user_login") or "").strip():
        problemas.append("user_login vazio (unique)")

    cpf = re.sub(r"\D", "", row.get("cpf") or "")
    if len(cpf) != 11:
        problemas.append(f"cpf inválido: {cpf!r} (11 dígitos esperados)")

    if tipo == "medico":
        if not (row.get("numero_crm") or "").strip():
            problemas.append("medico sem numero_crm")
        if not REGEX_UF.match((row.get("uf_crm") or "").strip()):
            problemas.append(f"uf_crm inválida: {row.get('uf_crm')!r}")
    if tipo == "enfermeiro":
        if not (row.get("numero_coren") or "").strip():
            problemas.append("enfermeiro sem numero_coren")
        if not REGEX_UF.match((row.get("uf_coren") or "").strip()):
            problemas.append(f"uf_coren inválida: {row.get('uf_coren')!r}")

    # dedupe contra o banco (constraints unique estourariam no commit final)
    if len(cpf) == 11 and repo.find_by_cpf_hash(hmac_sha256(cpf)):
        problemas.append("cpf já cadastrado (cpf_hash duplicado)")
    if row.get("user_login") and repo.find_by_user_login(row["user_login"].strip().lower()):
        problemas.append("user_login já cadastrado")
    if row.get("email") and repo.find_by_email(row["email"].strip().lower()):
        problemas.append("email já cadastrado")

    return problemas


# ----------------------------------------------------------------------------
# Função principal reutilizável
# ----------------------------------------------------------------------------
def seed_profissionais(empresa: int, csv_path=None, ate: int = None,
                       dry_run: bool = False, app=None) -> dict:
    """Executa a seed e devolve um relatório (não levanta exceção por linha).

    Retorno:
        {
          "ok": bool,               # True só se nenhuma linha falhou
          "dry_run": bool,
          "total": int,             # linhas lidas
          "inseridos": int,         # linhas válidas (gravadas só se ok e não dry_run)
          "commitado": bool,
          "erros": [{"linha": int, "profissional": str, "erro": str}, ...],
        }
    `linha` é o número da linha no arquivo CSV (cabeçalho = linha 1).
    Passe `app` se não estiver dentro de um app context.
    """
    ctx = app.app_context() if app is not None else contextlib.nullcontext()
    with ctx:
        return _executar(empresa, csv_path, ate, dry_run)


def _executar(empresa, csv_path, ate, dry_run) -> dict:
    resultado = {"ok": False, "dry_run": dry_run, "total": 0, "inseridos": 0,
                 "commitado": False, "erros": []}
    erros = resultado["erros"]
    repo = UsuarioRepository()

    # --- leitura do CSV ---
    caminho = Path(csv_path) if csv_path else CSV_PADRAO
    try:
        with open(caminho, newline="", encoding="utf-8") as f:
            leitor = csv.DictReader(f)
            faltando = COLUNAS_OBRIGATORIAS - set(leitor.fieldnames or [])
            if faltando:
                erros.append({"linha": 1, "profissional": "-",
                              "erro": f"colunas ausentes no CSV: {sorted(faltando)}"})
                return resultado
            rows = list(leitor)
    except FileNotFoundError:
        erros.append({"linha": 0, "profissional": "-", "erro": f"CSV não encontrado: {caminho}"})
        return resultado
    except Exception as e:
        erros.append({"linha": 0, "profissional": "-", "erro": f"falha lendo CSV: {type(e).__name__}: {e}"})
        return resultado

    if ate:
        rows = rows[:ate]
    resultado["total"] = len(rows)

    # hash calculado uma vez, reutilizado por todas as linhas
    try:
        hash_pronto = ph.hash(SENHA_PADRAO_SEED)
    except Exception as e:
        erros.append({"linha": 0, "profissional": "-",
                      "erro": f"falha gerando hash da senha padrão: {type(e).__name__}: {e}"})
        return resultado

    # --- processa linha a linha, cada uma em um SAVEPOINT ---
    for idx, row in enumerate(rows):
        linha = idx + 2
        nome = (row.get("nome_completo") or "?").strip()

        problemas = _validar_linha(row, repo)
        if problemas:
            erros.append({"linha": linha, "profissional": nome, "erro": "; ".join(problemas)})
            continue

        savepoint = db.session.begin_nested()
        try:
            usuario = _montar_usuario(row, empresa, hash_pronto)
            db.session.add(usuario)
            db.session.flush()  # -> usuario.id
            db.session.add(_montar_papel(row, usuario))

            savepoint.commit()
            resultado["inseridos"] += 1
        except Exception as e:
            savepoint.rollback()
            erros.append({"linha": linha, "profissional": nome,
                          "erro": f"{type(e).__name__}: {e}"})

    # --- fechamento: tudo ou nada ---
    if erros or dry_run:
        db.session.rollback()
    else:
        try:
            db.session.commit()
            resultado["commitado"] = True
        except Exception as e:
            db.session.rollback()
            erros.append({"linha": 0, "profissional": "-",
                          "erro": f"falha no commit final: {type(e).__name__}: {e}"})

    resultado["ok"] = not erros
    return resultado


def _imprimir_relatorio(r: dict, empresa: int):
    if r["ok"]:
        if r["dry_run"]:
            print(f"[dry-run] {r['inseridos']}/{r['total']} profissionais válidos (nada commitado).")
        else:
            print(f"OK: {r['inseridos']} profissionais inseridos na empresa {empresa}.")
        return
    print(f"FALHOU: {len(r['erros'])} erro(s) em {r['total']} linha(s); "
          f"nada foi gravado (rollback total).")
    for e in r["erros"]:
        print(f"  - linha {e['linha']} ({e['profissional']}): {e['erro']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--empresa", type=int, required=True)
    ap.add_argument("--csv", default=str(CSV_PADRAO))
    ap.add_argument("--ate", type=int, default=None, help="só as N primeiras linhas (teste)")
    ap.add_argument("--dry-run", action="store_true", help="monta tudo sem commitar")
    args = ap.parse_args()

    resultado = seed_profissionais(
        empresa=args.empresa, csv_path=args.csv, ate=args.ate, dry_run=args.dry_run,
    )
    _imprimir_relatorio(resultado, args.empresa)
    sys.exit(0 if resultado["ok"] else 1)


if __name__ == "__main__":
    main()
