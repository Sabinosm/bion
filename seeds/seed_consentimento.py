"""
Auxiliar para inserir consentimentos LGPD no banco (seed / importação de papel / testes).

Passa SEMPRE pelo ConsentimentoService (ativar_novo / dispensar_por_emergencia), então
valem as mesmas regras do sistema: schema Pydantic, "um ativo por paciente" (revoga o
anterior), uuid, datas em UTC. Não faz INSERT direto na tabela.

Uso (da raiz do projeto, com o .env carregado):

  # um consentimento manual (papel escaneado, portal, totem)
  python seed_consentimentos.py um --empresa 1 --usuario 7 \
      --paciente <uuid_paciente> --canal presencial-papel \
      --versao lgpd-v1.0-2026 --escopo pesquisa comunicacao \
      --pdf ./scan_termo.pdf

  # dispensa por emergência
  python seed_consentimentos.py emergencia --empresa 1 --usuario 7 \
      --paciente <uuid_paciente> --motivo "Paciente inconsciente na admissão"

  # em lote (JSON: lista de objetos, ver LOTE_EXEMPLO abaixo)
  python seed_consentimentos.py lote --empresa 1 --usuario 7 --arquivo lote.json

  Adicione --dry-run para validar tudo e desfazer no final (rollback).

Factory do Flask: defina APP_FACTORY="modulo:funcao" (padrão "src:create_app").
Se o seu create_app tiver outro caminho/assinatura, ajuste _criar_app().

Limite conhecido: o canal 'presencial-digital' NÃO é aceito aqui (só nasce do QR code,
com PDF assinado e trilha de auditoria). Para PDF de papel escaneado, --pdf só calcula o
hash_documento (SHA-256); o arquivo em si não é copiado para o storage.
"""
import argparse
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path

LOTE_EXEMPLO = [
    {
        "uuid_paciente": "…",
        "canal_coleta": "presencial-papel",       # presencial-papel | portal-online | totem
        "versao_termo": "lgpd-v1.0-2026",
        "escopo": ["pesquisa", "comunicacao"],    # códigos de ESCOPOS_VALIDOS (pode ser [])
        "pdf": "./scans/paciente1.pdf",           # opcional -> hash_documento
    },
    {"uuid_paciente": "…", "emergencia": True, "motivo": "Atendimento de urgência"},
]


def _criar_app():
    caminho = os.getenv("APP_FACTORY", "src:create_app")
    modulo, _, func = caminho.partition(":")
    return getattr(importlib.import_module(modulo), func)()


def sha256_arquivo(caminho: str) -> str:
    p = Path(caminho)
    if not p.is_file():
        raise FileNotFoundError(f"PDF não encontrado: {caminho}")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _montar_dados_manual(item: dict) -> dict:
    from src.domains.paciente.schemas.schema_consentimento_digital import ESCOPOS_VALIDOS

    escopo = list(dict.fromkeys(item.get("escopo") or []))
    invalidos = [e for e in escopo if e not in ESCOPOS_VALIDOS]
    if invalidos:
        raise ValueError(f"escopo(s) desconhecido(s): {', '.join(invalidos)}. "
                         f"Válidos: {', '.join(ESCOPOS_VALIDOS)}")
    dados = {
        "versao_termo": item["versao_termo"],
        "canal_coleta": item["canal_coleta"],
        # mesmo formato de chave do fluxo digital ({"escopo": [...]}), sem o bloco audit
        "escopo_consentimento": {"escopo": escopo},
    }
    if item.get("pdf"):
        dados["hash_documento"] = sha256_arquivo(item["pdf"])
    elif item.get("hash_documento"):
        dados["hash_documento"] = item["hash_documento"]
    return dados


def processar_item(svc, item: dict, id_usuario: int, id_empresa: int) -> str:
    """Insere UM consentimento (commit=False). Retorna uma descrição curta."""
    uuid_paciente = item["uuid_paciente"]
    if item.get("emergencia"):
        c = svc.dispensar_por_emergencia(
            uuid_paciente, {"motivo": item.get("motivo", "")}, id_usuario, id_empresa, commit=False
        )
    else:
        c = svc.registrar(
            uuid_paciente, _montar_dados_manual(item), id_usuario, id_empresa, commit=False
        )
    return f"{c.uuid} [{c.status}] canal={c.canal_coleta}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["um", "emergencia", "lote"])
    ap.add_argument("--empresa", type=int, required=True, help="id_empresa dona do paciente")
    ap.add_argument("--usuario", type=int, required=True, help="id_usuario que coletou (coletado_por)")
    ap.add_argument("--paciente", help="uuid do paciente (modos um/emergencia)")
    ap.add_argument("--canal", choices=["presencial-papel", "portal-online", "totem"])
    ap.add_argument("--versao", help="versao_termo, ex.: lgpd-v1.0-2026")
    ap.add_argument("--escopo", nargs="*", default=[])
    ap.add_argument("--pdf", help="PDF do termo (papel escaneado) para calcular hash_documento")
    ap.add_argument("--motivo", help="obrigatório em 'emergencia'")
    ap.add_argument("--arquivo", help="JSON do modo lote")
    ap.add_argument("--dry-run", action="store_true", help="valida e faz rollback no final")
    a = ap.parse_args(argv)

    if a.modo == "um":
        if not (a.paciente and a.canal and a.versao):
            ap.error("modo 'um' exige --paciente, --canal e --versao")
        itens = [{"uuid_paciente": a.paciente, "canal_coleta": a.canal, "versao_termo": a.versao,
                  "escopo": a.escopo, "pdf": a.pdf}]
    elif a.modo == "emergencia":
        if not (a.paciente and a.motivo):
            ap.error("modo 'emergencia' exige --paciente e --motivo")
        itens = [{"uuid_paciente": a.paciente, "emergencia": True, "motivo": a.motivo}]
    else:
        if not a.arquivo:
            ap.error("modo 'lote' exige --arquivo")
        itens = json.loads(Path(a.arquivo).read_text(encoding="utf-8"))

    app = _criar_app()
    with app.app_context():
        from src.models import db
        from src.core.exceptions import BionException
        from src.domains.paciente.services import ConsentimentoService

        svc = ConsentimentoService()
        ok, falhas = 0, []
        try:
            for i, item in enumerate(itens, 1):
                try:
                    print(f"[{i}/{len(itens)}] OK  {processar_item(svc, item, a.usuario, a.empresa)}")
                    ok += 1
                except (BionException, ValueError, KeyError, FileNotFoundError) as ex:
                    msg = getattr(ex, "message", None) or str(ex)
                    print(f"[{i}/{len(itens)}] ERRO {item.get('uuid_paciente')}: {msg}")
                    falhas.append(i)
            # Tudo-ou-nada: com qualquer falha (ou --dry-run) nada é gravado.
            if falhas or a.dry_run:
                db.session.rollback()
                motivo = "dry-run" if a.dry_run else f"{len(falhas)} falha(s)"
                print(f"\nRollback ({motivo}). Nada foi gravado. Válidos: {ok}.")
                return 1 if falhas else 0
            db.session.commit()
            print(f"\nCommit feito: {ok} consentimento(s) gravado(s).")
            return 0
        except Exception:
            db.session.rollback()
            raise


if __name__ == "__main__":
    sys.exit(main())