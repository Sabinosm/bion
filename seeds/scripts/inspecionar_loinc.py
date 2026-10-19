#!/usr/bin/env python3
"""Inspeciona os arquivos do LOINC ANTES de modelar o catálogo de exames (v2).

Só lê os arquivos (biblioteca padrão). Tudo é lido pelo NOME do cabeçalho.

Uso:
    python scripts/exames/inspecionar_loinc.py seeds/exames/loinc/Loinc.csv [seeds/exames/loinc/ptBR11LinguisticVariant.csv] [--top 500]

Cole a saída (ou os trechos principais) de volta no chat.
"""
import argparse
import csv
import sys
from collections import Counter, defaultdict

ESPERADAS = [
    "LOINC_NUM", "COMPONENT", "PROPERTY", "TIME_ASPCT", "SYSTEM", "SCALE_TYP", "METHOD_TYP",
    "CLASS", "CLASSTYPE", "LONG_COMMON_NAME", "DisplayName", "CONSUMER_NAME", "SHORTNAME", "STATUS",
    "ORDER_OBS", "PanelType", "EXAMPLE_UCUM_UNITS", "COMMON_TEST_RANK", "COMMON_ORDER_RANK",
]
csv.field_size_limit(sys.maxsize)


def ler(path):
    """Retorna (encoding, cabecalho, linhas[dict]). Tenta utf-8 e cai para latin-1."""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(path, encoding=enc, newline="") as f:
                leitor = csv.DictReader(f)
                cab = list(leitor.fieldnames or [])
                return enc, cab, [dict(r) for r in leitor]
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"Não consegui decodificar {path}")


def num(v):
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return None


def g(r, c):
    return (r.get(c) or "").strip()


def titulo(t):
    print(f"\n=== {t} ===")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("loinc_csv")
    ap.add_argument("ptbr_csv", nargs="?")
    ap.add_argument("--top", type=int, default=500)
    a = ap.parse_args()

    enc, cab, linhas = ler(a.loinc_csv)
    titulo("Loinc.csv")
    print(f"encoding: {enc} | linhas: {len(linhas)} | colunas: {len(cab)}")
    print("esperadas e AUSENTES:", [c for c in ESPERADAS if c not in cab] or "nenhuma")

    escopo = [r for r in linhas if g(r, "CLASSTYPE") == "1" and g(r, "STATUS") == "ACTIVE"]
    titulo("Escopo: CLASSTYPE=1 (laboratório) e STATUS=ACTIVE")
    print("total:", len(escopo))

    # ------------------------------------------------------------------
    # Pedíveis: COMMON_ORDER_RANK / ORDER_OBS / PanelType
    # ------------------------------------------------------------------
    titulo("PEDÍVEIS: COMMON_ORDER_RANK, ORDER_OBS, PanelType")
    print("ORDER_OBS no escopo:", dict(Counter(g(r, "ORDER_OBS") for r in escopo)))
    print("PanelType no escopo:", dict(Counter(g(r, "PanelType") for r in escopo)))
    com_ordem_geral = [r for r in linhas if (num(g(r, "COMMON_ORDER_RANK")) or 0) > 0]
    print("COMMON_ORDER_RANK > 0 no arquivo todo:", len(com_ordem_geral),
          "| por (CLASSTYPE, STATUS):", dict(Counter((g(r, "CLASSTYPE"), g(r, "STATUS")) for r in com_ordem_geral)))
    ped = sorted(
        [(num(g(r, "COMMON_ORDER_RANK")), r) for r in escopo if (num(g(r, "COMMON_ORDER_RANK")) or 0) > 0],
        key=lambda x: x[0],
    )
    print("no escopo com COMMON_ORDER_RANK > 0:", len(ped))
    if ped:
        print("menor/maior order rank:", ped[0][0], "/", ped[-1][0])
        print("\n40 de menor COMMON_ORDER_RANK:")
        for n, r in ped[:40]:
            print(f"  {n:>4} {g(r,'LOINC_NUM'):<9} {g(r,'ORDER_OBS'):<11} {g(r,'PanelType'):<10} {g(r,'CLASS'):<13} "
                  f"{g(r,'LONG_COMMON_NAME')[:55]} | DISPLAY={g(r,'DisplayName')[:35]}")
    print("\nDisplayName (inglês) preenchido no escopo:", sum(1 for r in escopo if g(r, "DisplayName")),
          "| CONSUMER_NAME (inglês) preenchido:", sum(1 for r in escopo if g(r, "CONSUMER_NAME")))
    print("amostra de CONSUMER_NAME/DisplayName nos pedíveis:")
    for n, r in ped[:8]:
        print(f"  {g(r,'LOINC_NUM'):<9} CONSUMER={g(r,'CONSUMER_NAME')[:40]!r} | DISPLAY={g(r,'DisplayName')[:40]!r}")

    # ------------------------------------------------------------------
    # COMMON_TEST_RANK (para comparar)
    # ------------------------------------------------------------------
    titulo("COMMON_TEST_RANK (volume de resultados nos EUA)")
    com_rank = sorted(
        [(num(g(r, "COMMON_TEST_RANK")), r) for r in escopo if (num(g(r, "COMMON_TEST_RANK")) or 0) > 0],
        key=lambda x: x[0],
    )
    print("com rank > 0:", len(com_rank), "| menor/maior:",
          (com_rank[0][0], com_rank[-1][0]) if com_rank else None)
    topo = [r for _, r in com_rank[:a.top]]
    por_comp = defaultdict(list)
    for r in topo:
        por_comp[g(r, "COMPONENT")].append(r)
    print(f"top {a.top}: códigos {len(topo)} | COMPONENT distintos {len(por_comp)}")

    # ------------------------------------------------------------------
    # pt-BR
    # ------------------------------------------------------------------
    if a.ptbr_csv:
        enc2, cab2, linhas2 = ler(a.ptbr_csv)
        titulo("Arquivo pt-BR")
        print(f"encoding: {enc2} | linhas: {len(linhas2)}")
        if "LOINC_NUM" not in cab2:
            print("!! sem coluna LOINC_NUM; colunas:", cab2)
            return
        pt = {g(r, "LOINC_NUM"): r for r in linhas2}
        partes = ["COMPONENT", "PROPERTY", "SYSTEM", "SCALE_TYP", "METHOD_TYP"]

        def cobertura(rotulo, rows):
            par = [(r, pt.get(g(r, "LOINC_NUM"), {})) for r in rows]
            conta = lambda f: sum(1 for r, t in par if f(r, t))
            print(f"\ncobertura em {rotulo} ({len(rows)} códigos):")
            print("  linha existe:", conta(lambda r, t: bool(t)))
            print("  COMPONENT traduzido (preenchido e != inglês):",
                  conta(lambda r, t: bool(g(t, "COMPONENT")) and g(t, "COMPONENT") != g(r, "COMPONENT")))
            print("  SYSTEM traduzido:",
                  conta(lambda r, t: bool(g(t, "SYSTEM")) and g(t, "SYSTEM") != g(r, "SYSTEM")))
            print("  SHORTNAME preenchido:", conta(lambda r, t: bool(g(t, "SHORTNAME"))))

        cobertura("pedíveis (COMMON_ORDER_RANK > 0)", [r for _, r in ped])
        cobertura(f"top {a.top} por COMMON_TEST_RANK", topo)

        print("\nPARTES em inglês x português (12 primeiros pedíveis):")
        for n, r in ped[:12]:
            t = pt.get(g(r, "LOINC_NUM"), {})
            print(f"  {g(r,'LOINC_NUM'):<9} EN: {g(r,'COMPONENT')[:32]!r} | {g(r,'PROPERTY')!r} | {g(r,'SYSTEM')!r}")
            print(f"            PT: {g(t,'COMPONENT')[:32]!r} | {g(t,'PROPERTY')!r} | {g(t,'SYSTEM')!r}"
                  f" | SHORT={g(t,'SHORTNAME')[:30]!r}")


if __name__ == "__main__":
    main()
