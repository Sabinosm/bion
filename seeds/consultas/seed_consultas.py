"""seed_consultas.py -- Cria Consultas de teste seguindo o fluxo real.

Uso (CLI):
    python -m src.seeds.seed_consultas --empresa 1
    python -m src.seeds.seed_consultas --empresa 1 --dry-run

Uso (código):
    from src.seeds.seed_consultas import seed_consultas
    resultado = seed_consultas(empresa=1, dry_run=True, app=app)

FLUXO SIMULADO (parte 1 de 3 -- veja seed_atendimentos.py):
  1. Lê seed_consultas.csv: uma linha por consulta a criar, cada uma com um
     CENÁRIO que define o estado final esperado (ex: 'encerrada-alta',
     'em-atendimento'). Pacientes NÃO vêm do CSV: são reaproveitados do
     banco, em ordem de id (já criados pelo seed_pacientes.py, sempre
     status='ativo'), um paciente por linha.
  2. Para cada linha: cria a Consulta (status inicial 'aguardando-triagem',
     como ConsultaService.abrir faria) e DISPENSA O CONSENTIMENTO por
     emergência (ConsentimentoService.dispensar_por_emergencia_id -- o mesmo
     caminho de paciente_nao_identificado), senão nenhum atendimento abriria.
  3. NÃO cria atendimentos nem encerra nada aqui: quem fecha as consultas
     dos cenários 'encerrada-*'/'evasao' é o seed_atendimentos.py, DEPOIS
     de criar as triagens. Rodar fora de ordem deixa o cenário errado.

REGRAS DO SEED (acordadas):
  - Sem reavaliação, sem prescrição. Avaliação médica NUNCA é finalizada:
    cenário 'em-atendimento' deixa a avaliação em-andamento de propósito.
  - Consultas encerradas só têm triagem no histórico (encerrar bloqueia com
    atendimento em andamento), exceto 'evasao', que cancela pendentes.
  - Máx. 1 consulta aberta por paciente: linha cujo paciente já tenha
    consulta aberta (de uso real) é registrada como erro.

Este módulo expõe `carregar_plano` e `pacientes_elegiveis`, que o
seed_atendimentos.py reutiliza para achar a mesma consulta criada aqui.
"""

import argparse
import contextlib
import csv
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models import db
from src.models.pacientes import Paciente
from src.models.clinico import Consulta
from src.domains.consulta.repository import ConsultaRepository
from src.domains.usuario.repository import UsuarioRepository
# ajuste o caminho se o ConsentimentoService morar em outro lugar:
from src.domains.paciente.services.consentimento_service import ConsentimentoService

CSV_PADRAO = Path(__file__).with_name("seed_consultas.csv")

# cenário -> desfecho esperado ("" = consulta continua aberta; o encerramento
# sai na parte 2, depois dos atendimentos). MANTER SINCRONIZADO com o CSV.
CENARIOS_ENCERRADOS = {
    "encerrada-alta": "alta",
    "encerrada-internacao": "internacao",
    "encerrada-transferencia": "transferencia",
    "encerrada-obito": "obito",
    "evasao": "evasao",
}
CENARIOS_ABERTOS = {
    "aguardando-triagem": "aguardando-triagem",
    "em-triagem": "em-triagem",
    "aguardando-medico": "aguardando-medico",
    "em-atendimento": "em-atendimento",
}
CENARIOS_VALIDOS = set(CENARIOS_ENCERRADOS) | set(CENARIOS_ABERTOS)
ORIGENS_VALIDAS = ("espontanea", "SAMU", "transferencia", "regulacao")

MOTIVO_DISPENSA = "seed de dados sintéticos"


def _msg_erro(e: Exception) -> str:
    return f"{type(e).__name__}: {getattr(e, 'orig', None) or e}"


# ----------------------------------------------------------------------------
# Plano (CSV) -- reutilizado pelo seed_atendimentos.py
# ----------------------------------------------------------------------------
def carregar_plano(csv_path=None, ate: int = None):
    """Lê o CSV de cenários. Devolve (linhas, erros). Cada linha é um dict
    com cenario/origem_encaminhamento/desfecho_final/dias_atras + 'linha'
    (nº no arquivo, cabeçalho = 1)."""
    caminho = Path(csv_path) if csv_path else CSV_PADRAO
    erros = []
    try:
        with open(caminho, newline="", encoding="utf-8") as f:
            leitor = csv.DictReader(f)
            faltando = {"cenario", "origem_encaminhamento", "desfecho_final", "dias_atras"} - set(leitor.fieldnames or [])
            if faltando:
                return [], [f"colunas ausentes no CSV: {sorted(faltando)}"]
            linhas = []
            for i, row in enumerate(leitor, start=2):
                row["linha"] = i
                linhas.append(row)
    except FileNotFoundError:
        return [], [f"CSV não encontrado: {caminho}"]
    except Exception as e:
        return [], [f"falha lendo CSV: {_msg_erro(e)}"]

    if ate:
        linhas = linhas[:ate]

    for row in linhas:
        if row["cenario"] not in CENARIOS_VALIDOS:
            erros.append(f"linha {row['linha']}: cenário inválido {row['cenario']!r}; use um de: {sorted(CENARIOS_VALIDOS)}")
        if row["origem_encaminhamento"] not in ORIGENS_VALIDAS:
            erros.append(f"linha {row['linha']}: origem inválida {row['origem_encaminhamento']!r}")
        try:
            row["dias_atras"] = int(row["dias_atras"] or 0)
        except ValueError:
            erros.append(f"linha {row['linha']}: dias_atras deve ser inteiro")
        esperado = CENARIOS_ENCERRADOS.get(row["cenario"], "")
        if (row["desfecho_final"] or "") != esperado:
            erros.append(f"linha {row['linha']}: desfecho_final deve ser {esperado!r} para o cenário {row['cenario']!r}")
    return linhas, erros


# ----------------------------------------------------------------------------
# Pacientes elegíveis -- MESMA ordem aqui e no seed_atendimentos.py
# ----------------------------------------------------------------------------
def pacientes_elegiveis(id_empresa: int):
    """Pacientes da empresa com status 'ativo', em ordem de id (o seed de
    atendimentos reaproveita esta função para achar a mesma consulta criada
    aqui: linha i -> paciente i -> consulta do paciente)."""
    return (
        Paciente.query
        .filter_by(id_empresa=id_empresa, status="ativo")
        .order_by(Paciente.id)
        .all()
    )


# ----------------------------------------------------------------------------
# Função principal
# ----------------------------------------------------------------------------
def seed_consultas(empresa: int, csv_path="seeds/consultas/seed_consultas.csv", ate: int = None,
                   dry_run: bool = False, id_usuario: int = None, app=None) -> dict:
    """Cria as consultas + dispensas de consentimento. Relatório no mesmo
    formato dos demais seeds."""
    ctx = app.app_context() if app is not None else contextlib.nullcontext()
    with ctx:
        return _executar(empresa, csv_path, ate, dry_run, id_usuario)


def _executar(empresa, csv_path, ate, dry_run, id_usuario) -> dict:
    resultado = {"ok": False, "dry_run": dry_run, "total": 0, "inseridos": 0,
                 "commitado": False, "erros": [], "avisos": []}
    erros = resultado["erros"]
    repo = ConsultaRepository()

    linhas, erros_plano = carregar_plano(csv_path, ate)
    erros.extend({"linha": 0, "paciente": "-", "erro": m} for m in erros_plano)
    if erros_plano:
        resultado["total"] = len(linhas)
        return resultado
    resultado["total"] = len(linhas)

    # quem "inicia" a consulta e dispensa o consentimento: um admin da
    # empresa; se não houver, qualquer profissional ativo serve.
    admin_id = id_usuario
    if admin_id is None:
        admins = UsuarioRepository().find_admins(empresa)
        admin_id = admins[0].id if admins else None
    if admin_id is None:
        ids = UsuarioRepository().find_ids_profissionais(empresa, limit=1)
        admin_id = ids[0] if ids else None
    if admin_id is None:
        erros.append({"linha": 0, "paciente": "-", "erro": "empresa sem nenhum usuário para iniciar as consultas"})
        return resultado

    pacientes = pacientes_elegiveis(empresa)
    if len(pacientes) < len(linhas):
        resultado["avisos"].append(
            f"só há {len(pacientes)} pacientes ativos para {len(linhas)} linhas do CSV; "
            f"as linhas excedentes serão registradas como erro")

    consentimento_svc = ConsentimentoService()

    for idx, row in enumerate(linhas):
        if idx >= len(pacientes):
            erros.append({"linha": row["linha"], "paciente": "-",
                          "erro": "pacientes ativos esgotados; rode o seed_pacientes primeiro"})
            continue
        paciente = pacientes[idx]
        nome = paciente.pessoal.nome_completo if getattr(paciente, "pessoal", None) else f"paciente {paciente.id}"

        # 1 consulta aberta por paciente (regra do sistema)
        if repo.find_aberta_por_paciente(paciente.id, empresa):
            erros.append({"linha": row["linha"], "paciente": nome,
                          "erro": "paciente já possui consulta aberta (de uso real?)"})
            continue

        savepoint = db.session.begin_nested()
        try:
            # data de início: 'dias_atras' no passado (consultas encerradas)
            # ou hoje cedo (consultas abertas). Jitter determinístico por linha.
            agora = datetime.now(timezone.utc)
            inicio = agora - timedelta(
                days=row["dias_atras"],
                hours=(idx * 7) % 9 if not row["dias_atras"] else (idx * 3) % 8,
            )
            consulta = Consulta(
                id_paciente=paciente.id,
                id_empresa=empresa,
                origem_encaminhamento=row["origem_encaminhamento"],
                status_consulta="aguardando-triagem",  # status inicial real
                data_hora_inicio=inicio,
                iniciada_por=admin_id,
            )
            repo.save(consulta, commit=False)  # flush -> consulta.id

            # sem consentimento nenhum atendimento abre (exigir_consentimento)
            consentimento_svc.dispensar_por_emergencia_id(
                paciente.id, {"motivo": MOTIVO_DISPENSA}, admin_id, commit=False
            )

            savepoint.commit()
            resultado["inseridos"] += 1
        except Exception as e:
            savepoint.rollback()
            erros.append({"linha": row["linha"], "paciente": nome, "erro": _msg_erro(e)})

    if erros or dry_run:
        db.session.rollback()
    else:
        try:
            db.session.commit()
            resultado["commitado"] = True
        except Exception as e:
            db.session.rollback()
            erros.append({"linha": 0, "paciente": "-", "erro": f"falha no commit final: {_msg_erro(e)}"})

    resultado["ok"] = not erros
    return resultado


def _imprimir_relatorio(r: dict, empresa: int):
    for aviso in r.get("avisos", []):
        print(f"AVISO: {aviso}")
    if r["ok"]:
        if r["dry_run"]:
            print(f"[dry-run] {r['inseridos']}/{r['total']} consultas válidas (nada commitado).")
        else:
            print(f"OK: {r['inseridos']} consultas criadas na empresa {empresa} "
                  f"(consentimentos dispensados). Agora rode o seed_atendimentos.")
        return
    print(f"FALHOU: {len(r['erros'])} erro(s) em {r['total']} linha(s); nada foi gravado.")
    for e in r["erros"]:
        print(f"  - linha {e['linha']} ({e['paciente']}): {e['erro']}")


def main(empresa, id_usuario, dry_run=False):
    ap = argparse.ArgumentParser()
    ap.add_argument("--empresa", type=int, required=True)
    ap.add_argument("--ate", type=int, default=None, help="só as N primeiras linhas (teste)")
    ap.add_argument("--usuario", type=int, default=None,
                    help="id_usuario que inicia as consultas e dispensa consentimentos (padrão: primeiro admin da empresa)")
    ap.add_argument("--dry-run", action="store_true", help="monta tudo sem commitar")
    args = ap.parse_args()

    resultado = seed_consultas(
        empresa=empresa, ate=args.ate,
        dry_run=dry_run, id_usuario=id_usuario,
    )
    _imprimir_relatorio(resultado, args.empresa)
    sys.exit(0 if resultado["ok"] else 1)


if __name__ == "__main__":
    main()
