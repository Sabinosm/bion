"""seed_pacientes.py -- Popula pacientes de teste a partir de CSV.

Uso (CLI):
    python -m src.seeds.seed_pacientes --empresa 1
    python -m src.seeds.seed_pacientes --empresa 1 --dry-run   # valida sem commitar
    python -m src.seeds.seed_pacientes --empresa 1 --ate 20    # só as 20 primeiras linhas
    python -m src.seeds.seed_pacientes --empresa 1 --usuario 5 # cadastrado_por fixo (senão sorteia)

Uso (código):
    from src.seeds.seed_pacientes import seed_pacientes
    resultado = seed_pacientes(empresa=1, dry_run=True, app=app)
    if not resultado["ok"]:
        for e in resultado["erros"]:
            print(e["linha"], e["paciente"], e["erro"])

Como funciona:
  1. Lê seed_pacientes.csv (uma linha por paciente).
  2. Cada linha roda dentro de um SAVEPOINT: se uma linha falha, só ela é
     desfeita e o erro é registrado; as demais continuam sendo validadas.
     Assim você recebe TODOS os erros de uma vez, não só o primeiro.
  3. Se houve qualquer erro (ou --dry-run) -> rollback total. Senão -> um
     único commit no final (tudo atômico, ou nada).

Mapeamento conforme os models:
  - Paciente: bairro, id_regiao_geografica, data_primeiro_atendimento
    (NOT NULL), cadastrado_por, sexo_biologico, status, peso, altura...
  - PacienteDadosPessoais: cpf (cifrado), cpf_hash, rg, telefone, email,
    logradouro, numero_residencia, cep, contato_emergencia_*.
  - uuid: gerado pelo default do model (não é passado aqui).
"""

import argparse
import contextlib
import csv
import random
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models import db
from src.models.pacientes import (
    Paciente, PacienteDadosPessoais, Alergia, ReacaoAlergia,
    DoencaCronica, MedicamentoEmUso, ObservacaoTipoSanguineo,
)
from src.domains.paciente.repositories.paciente_repository import PacienteRepository
from src.domains.paciente.repositories.alergia_repository import AlergiaRepository
from src.domains.paciente.repositories.reacao_alergia_repository import ReacaoAlergiaRepository
from src.domains.paciente.repositories.doenca_cronica_repository import DoencaCronicaRepository
from src.domains.paciente.repositories.medicamento_em_uso_repository import MedicamentoEmUsoRepository
from src.domains.paciente.repositories.obs_tipo_sanguineo_repository import ObservacaoTipoSanguineoRepository
# ajuste o caminho para o real do seu projeto:
from src.domains.usuario.repository import UsuarioRepository

# CPF/RG são cifrados (AES-256-GCM) e o CPF tem hash HMAC -- o seed precisa
# usar os MESMOS helpers do runtime, senão find_por_cpf_hash nunca acha
# esses pacientes. Ajuste os nomes se divergirem dos reais.
from src.core.security import aes_encrypt, hmac_sha256

CSV_PADRAO = Path(__file__).with_name("seed_pacientes.csv")

# Campos de PacienteDadosPessoais gravados cifrados. Os tamanhos das colunas
# (telefone/cep/email = 200-500) sugerem que o runtime pode cifrar mais
# campos; se for o caso, basta adicionar o nome aqui.
CAMPOS_CIFRADOS = {"cpf", "rg"}

SEXOS = {"M", "F", "I"}
STATUS = {"ativo", "inativo", "obito"}
COLUNAS_OBRIGATORIAS = {
    "sexo_biologico", "data_nascimento", "peso", "altura",
    "data_primeiro_atendimento", "status", "falecido", "data_obito",
    "nome_completo", "cpf", "telefone", "email", "logradouro",
    "numero_residencia", "cep", "rg", "bairro", "contato_emergencia",
    "alergias", "doencas_cronicas", "medicamentos_em_uso", "tipo_sanguineo",
}


# ----------------------------------------------------------------------------
# Conversores
# ----------------------------------------------------------------------------
def _d(v: str):
    return v or None


def _dt(v: str):
    return date.fromisoformat(v) if v else None


def _f(v: str):
    return float(v) if v else None


def _i(v: str):
    return int(v) if v else None


def _bool(v: str):
    return (v or "").strip().lower() in ("1", "true", "t", "sim")


def _regioes_existentes() -> set:
    """IDs reais da tabela regiao_geografica (FK de Paciente)."""
    try:
        res = db.session.execute(db.text("SELECT id_regiao_geografica FROM regiao_geografica"))
        return {r[0] for r in res}
    except Exception:
        db.session.rollback()
        return set()


# Aproximação por 1º dígito do CEP. Só vale se o id existir na tabela
# regiao_geografica; caso contrário vira NULL (evita violar a FK).
_REGIAO_POR_PREFIXO = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 5, 6: 4, 7: 3, 8: 5, 9: 2}


def _regiao_por_cep(cep: str, regioes_validas: set):
    digitos = "".join(c for c in (cep or "") if c.isdigit())
    if not digitos:
        return None
    id_regiao = _REGIAO_POR_PREFIXO.get(int(digitos[0]))
    return id_regiao if id_regiao in regioes_validas else None


# ----------------------------------------------------------------------------
# MAPEAMENTO CSV -> MODEL
# CAMPOS[campo_csv] = (nome_no_model, conversor)
# ----------------------------------------------------------------------------
CAMPOS_PACIENTE = {
    "sexo_biologico": ("sexo_biologico", str),
    "data_nascimento": ("data_nascimento", _dt),
    "peso": ("peso", _f),
    "altura": ("altura", _i),
    "data_primeiro_atendimento": ("data_primeiro_atendimento", _dt),
    "status": ("status", str),
    "falecido": ("falecido", _bool),
    "data_obito": ("data_obito", _dt),
    "bairro": ("bairro", _d),  # bairro mora em Paciente, não em DadosPessoais
}

CAMPOS_PESSOAL = {
    "nome_completo": ("nome_completo", str),
    "telefone": ("telefone", _d),
    "email": ("email", _d),
    "logradouro": ("logradouro", _d),
    "numero_residencia": ("numero_residencia", _d),
    "cep": ("cep", _d),
}


def _montar_paciente(row: dict, id_empresa: int, id_usuario, regioes: set) -> Paciente:
    kwargs = {model: conv(row[csv_]) for csv_, (model, conv) in CAMPOS_PACIENTE.items()}
    kwargs["id_empresa"] = id_empresa
    kwargs["cadastrado_por"] = id_usuario
    kwargs["id_regiao_geografica"] = _regiao_por_cep(row["cep"], regioes)
    # data_primeiro_atendimento é NOT NULL no model; o CSV deixa ~15% vazio.
    if kwargs["data_primeiro_atendimento"] is None:
        kwargs["data_primeiro_atendimento"] = date.today()
    return Paciente(**kwargs)


def _montar_pessoal(row: dict, paciente: Paciente, id_empresa: int) -> PacienteDadosPessoais:
    kwargs = {model: conv(row[csv_]) for csv_, (model, conv) in CAMPOS_PESSOAL.items()}
    if row["contato_emergencia"]:
        nome, tel = row["contato_emergencia"].split("|")
        kwargs["contato_emergencia_nome"] = nome
        kwargs["contato_emergencia_telefone"] = tel
    kwargs["id_empresa"] = id_empresa

    cpf = row["cpf"]
    rg = row["rg"] or None
    kwargs["cpf"] = aes_encrypt(cpf) if "cpf" in CAMPOS_CIFRADOS else cpf
    kwargs["cpf_hash"] = hmac_sha256(cpf)  # hash sempre sobre o CPF em claro
    kwargs["rg"] = aes_encrypt(rg) if (rg and "rg" in CAMPOS_CIFRADOS) else rg
    return PacienteDadosPessoais(paciente=paciente, **kwargs)


# ----------------------------------------------------------------------------
# Entidades relacionadas (campos compostos do CSV)
#   alergias:            itens "substancia^manifestacao^gravidade^descricao^data"
#                        separados por ';' ou '|'. Itens com 5 campos abrem/continuam
#                        uma alergia (agrupada por substância); itens com 4 campos
#                        (manifestacao^gravidade^descricao^data) são reações extras
#                        da última substância.
#   doencas_cronicas:    "CID^descricao^desde^status^observacoes;..."
#   medicamentos_em_uso: "descricao^dose^frequencia^desde;..."
# ----------------------------------------------------------------------------
def _items(composto: str):
    if not composto:
        return []
    return [item.split("^") for item in composto.split(";") if item]


def _parse_alergias(composto: str) -> dict:
    grupos: dict = {}
    atual = None
    for item in re.split(r"[|;]", composto or ""):
        if not item.strip():
            continue
        campos = item.split("^")
        if len(campos) == 5:
            atual = campos[0]
            grupos.setdefault(atual, []).append(campos[1:])
        elif len(campos) == 4 and atual:
            grupos[atual].append(campos)
        else:
            raise ValueError(f"alergias: item mal formatado: {item!r}")
    return grupos


def _semear_alergias(row, paciente):
    for substancia, reacoes in _parse_alergias(row["alergias"]).items():
        alergia = Alergia(
            id_paciente=paciente.id, substancia=substancia, flag_confirmado=True,
        )
        AlergiaRepository().save(alergia, commit=False)  # flush -> alergia.id
        for manifestacao, gravidade, descricao, data_oc in reacoes:
            ReacaoAlergiaRepository().save(ReacaoAlergia(
                id_alergia=alergia.id, manifestacao=manifestacao, gravidade=gravidade,
                descricao=descricao or None,
                data_ocorrencia=date.fromisoformat(data_oc),
            ), commit=False)


def _semear_doencas(row, paciente):
    for cid, descricao, desde, status, obs in _items(row["doencas_cronicas"]):
        DoencaCronicaRepository().save(DoencaCronica(
            id_paciente=paciente.id, codigo_cid10=cid, descricao_cid10=descricao,
            desde=date.fromisoformat(desde), status=status,
            observacoes=obs or None,
        ), commit=False)


def _semear_medicamentos(row, paciente):
    for descricao, dose, frequencia, desde in _items(row["medicamentos_em_uso"]):
        MedicamentoEmUsoRepository().save(MedicamentoEmUso(
            id_paciente=paciente.id, descricao=descricao,
            dose=dose or None, frequencia=frequencia or None,
            desde=date.fromisoformat(desde), status_uso="ativo",
            id_atendimento_origem=None,  # seed não tem atendimento; ajustar se NOT NULL
        ), commit=False)


def _semear_tipo_sanguineo(row, paciente):
    if row["tipo_sanguineo"]:
        ObservacaoTipoSanguineoRepository().save(ObservacaoTipoSanguineo(
            id_paciente=paciente.id, tipo_sanguineo=row["tipo_sanguineo"],
            data_registro=date.today(), id_atendimento_origem=None,  # ajustar se NOT NULL
        ), commit=False)


# ----------------------------------------------------------------------------
# Sorteio de profissionais para Paciente.cadastrado_por
# ----------------------------------------------------------------------------
def random_user_ids(id_empresa: int, tamanho: int = 100) -> list:
    """Devolve `tamanho` ids de profissionais da empresa, embaralhados.

    Pega até `tamanho` ids (se houver só 5, usa os 5). Para completar a
    lista, repete os ids em rodadas, embaralhando a ordem a cada rodada
    (assim ninguém concentra todos os cadastros). Sem nenhum profissional,
    devolve uma lista de None (cadastrado_por fica NULL).
    """
    ids = UsuarioRepository().find_ids_profissionais(id_empresa, limit=tamanho)
    if not ids:
        return [None] * tamanho

    pool: list = []
    while len(pool) < tamanho:
        rodada = ids[:]
        random.shuffle(rodada)
        pool.extend(rodada)
    return pool[:tamanho]


# ----------------------------------------------------------------------------
# Validação amigável (antes de tocar no banco)
# ----------------------------------------------------------------------------
def _validar_linha(row: dict) -> list:
    problemas = []
    if row.get("sexo_biologico") not in SEXOS:
        problemas.append(f"sexo_biologico inválido: {row.get('sexo_biologico')!r} (esperado M/F/I)")
    if row.get("status") not in STATUS:
        problemas.append(f"status inválido: {row.get('status')!r} (esperado ativo/inativo/obito)")
    if not (row.get("nome_completo") or "").strip():
        problemas.append("nome_completo vazio (NOT NULL)")
    if not (row.get("cpf") or "").strip():
        problemas.append("cpf vazio (cpf_hash é NOT NULL)")
    if row.get("status") == "obito" and not (_bool(row.get("falecido")) and row.get("data_obito")):
        problemas.append("status=obito exige falecido=1 e data_obito preenchida")
    return problemas


# ----------------------------------------------------------------------------
# Função principal reutilizável
# ----------------------------------------------------------------------------
def seed_pacientes(empresa: int, csv_path=None, ate: int = None,
                   dry_run: bool = False, id_usuario: int = None, app=None) -> dict:
    """Executa a seed e devolve um relatório (não levanta exceção por linha).

    Retorno:
        {
          "ok": bool,               # True só se nenhuma linha falhou
          "dry_run": bool,
          "total": int,             # linhas lidas
          "inseridos": int,         # linhas válidas (gravadas só se ok e não dry_run)
          "commitado": bool,
          "erros": [{"linha": int, "paciente": str, "erro": str}, ...],
        }
    `linha` é o número da linha no arquivo CSV (cabeçalho = linha 1).
    Passe `app` se não estiver dentro de um app context.
    """
    ctx = app.app_context() if app is not None else contextlib.nullcontext()
    with ctx:
        return _executar(empresa, csv_path, ate, dry_run, id_usuario)


def _executar(empresa, csv_path, ate, dry_run, id_usuario) -> dict:
    resultado = {"ok": False, "dry_run": dry_run, "total": 0, "inseridos": 0,
                 "commitado": False, "erros": []}
    erros = resultado["erros"]

    # --- leitura do CSV ---
    caminho = Path(csv_path) if csv_path else CSV_PADRAO
    try:
        with open(caminho, newline="", encoding="utf-8") as f:
            leitor = csv.DictReader(f)
            faltando = COLUNAS_OBRIGATORIAS - set(leitor.fieldnames or [])
            if faltando:
                erros.append({"linha": 1, "paciente": "-",
                              "erro": f"colunas ausentes no CSV: {sorted(faltando)}"})
                return resultado
            rows = list(leitor)
    except FileNotFoundError:
        erros.append({"linha": 0, "paciente": "-", "erro": f"CSV não encontrado: {caminho}"})
        return resultado
    except Exception as e:
        erros.append({"linha": 0, "paciente": "-", "erro": f"falha lendo CSV: {type(e).__name__}: {e}"})
        return resultado

    if ate:
        rows = rows[:ate]
    resultado["total"] = len(rows)

    regioes = _regioes_existentes()
    repo_pac = PacienteRepository()

    # --usuario fixo tem prioridade; senão sorteia entre médicos/enfermeiros
    if id_usuario is not None:
        pool_usuarios = [id_usuario] * len(rows)
    else:
        pool_usuarios = random_user_ids(empresa, tamanho=len(rows))

    # --- processa linha a linha, cada uma em um SAVEPOINT ---
    for idx, row in enumerate(rows):
        linha = idx + 2
        nome = (row.get("nome_completo") or "?").strip()

        problemas = _validar_linha(row)
        if problemas:
            erros.append({"linha": linha, "paciente": nome, "erro": "; ".join(problemas)})
            continue

        savepoint = db.session.begin_nested()
        try:
            paciente = _montar_paciente(row, empresa, pool_usuarios[idx], regioes)
            repo_pac.save(paciente, commit=False)  # flush -> paciente.id
            repo_pac.save(_montar_pessoal(row, paciente, empresa), commit=False)

            _semear_alergias(row, paciente)
            _semear_doencas(row, paciente)
            _semear_medicamentos(row, paciente)
            _semear_tipo_sanguineo(row, paciente)

            savepoint.commit()
            resultado["inseridos"] += 1
        except Exception as e:
            savepoint.rollback()
            erros.append({"linha": linha, "paciente": nome,
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
            erros.append({"linha": 0, "paciente": "-",
                          "erro": f"falha no commit final: {type(e).__name__}: {e}"})

    resultado["ok"] = not erros
    return resultado


def _imprimir_relatorio(r: dict, empresa: int):
    if r["ok"]:
        if r["dry_run"]:
            print(f"[dry-run] {r['inseridos']}/{r['total']} pacientes válidos (nada commitado).")
        else:
            print(f"OK: {r['inseridos']} pacientes inseridos na empresa {empresa}.")
        return
    print(f"FALHOU: {len(r['erros'])} erro(s) em {r['total']} linha(s); "
          f"nada foi gravado (rollback total).")
    for e in r["erros"]:
        print(f"  - linha {e['linha']} ({e['paciente']}): {e['erro']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--empresa", type=int, required=True)
    ap.add_argument("--csv", default=str(CSV_PADRAO))
    ap.add_argument("--ate", type=int, default=None, help="só as N primeiras linhas (teste)")
    ap.add_argument("--usuario", type=int, default=None,
                    help="id_usuario fixo para Paciente.cadastrado_por (padrão: sorteia entre médicos/enfermeiros da empresa)")
    ap.add_argument("--dry-run", action="store_true", help="monta tudo sem commitar")
    args = ap.parse_args()

    resultado = seed_pacientes(
        empresa=args.empresa, csv_path=args.csv, ate=args.ate,
        dry_run=args.dry_run, id_usuario=args.usuario,
    )
    _imprimir_relatorio(resultado, args.empresa)
    sys.exit(0 if resultado["ok"] else 1)


if __name__ == "__main__":
    main()