#!/usr/bin/env python3
"""Sugere candidatos de código LOINC para cada exame laboratorial da lista.

NÃO decide nada: gera um CSV com até N candidatos por exame (ordenados por uso)
para um profissional de saúde escolher. Os termos de busca da lista (coluna
busca_loinc) são PISTAS em inglês, não códigos.

Uso:
    python scripts/exames/sugerir_loinc.py seeds/exames/loinc/Loinc.csv seeds/exames/exames_brasil_candidatos.csv seeds/exames/candidatos_loinc.csv [--n 8]

Regras de busca (coluna busca_loinc):
  - alternativas separadas por '|'  -> basta uma casar
  - termos unidos por '+'           -> todos precisam casar (ex.: Protein+24 hour)
  - casa em COMPONENT ou LONG_COMMON_NAME, sem diferenciar maiúsculas
  - sistema_loinc (opcional, separado por '|') filtra pelo SYSTEM do LOINC
  - painel = s  -> só PanelType=Panel ; painel = n -> exclui painéis
Escopo: CLASSTYPE=1 (laboratório) e STATUS=ACTIVE.
Ordem: componente idêntico à busca, depois COMMON_ORDER_RANK, depois COMMON_TEST_RANK.
"""
import argparse
import csv
import sys

csv.field_size_limit(sys.maxsize)
INF = 10 ** 9


def num(v):
    try:
        n = int(float(str(v).strip()))
        return n if n > 0 else None
    except (ValueError, TypeError):
        return None


def carregar_loinc(caminho):
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        obrig = ["LOINC_NUM", "COMPONENT", "SYSTEM", "CLASSTYPE", "STATUS", "LONG_COMMON_NAME", "PanelType",
                 "COMMON_ORDER_RANK", "COMMON_TEST_RANK"]
        faltando = [c for c in obrig if c not in (leitor.fieldnames or [])]
        if faltando:
            raise SystemExit(f"{caminho}: colunas ausentes {faltando}")
        linhas = []
        for r in leitor:
            if (r["CLASSTYPE"] or "").strip() == "1" and (r["STATUS"] or "").strip() == "ACTIVE":
                r["_texto"] = f"{r['COMPONENT']} {r['LONG_COMMON_NAME']}".lower()
                r["_comp"] = (r["COMPONENT"] or "").strip().lower()
                linhas.append(r)
    return linhas


def candidatos(loinc, busca, sistemas, painel):
    alternativas = [[t.strip().lower() for t in alt.split("+") if t.strip()]
                    for alt in busca.split("|") if alt.strip()]
    sis = {s.strip().lower() for s in sistemas.split("|") if s.strip()}
    achados = []
    for r in loinc:
        if not any(all(t in r["_texto"] for t in alt) for alt in alternativas):
            continue
        if sis and (r["SYSTEM"] or "").strip().lower() not in sis:
            continue
        eh_painel = (r.get("PanelType") or "").strip() == "Panel"
        if painel == "s" and not eh_painel:
            continue
        if painel == "n" and eh_painel:
            continue
        exato = any(len(alt) == 1 and alt[0] == r["_comp"] for alt in alternativas)
        achados.append(r | {"_exato": exato})
    achados.sort(key=lambda r: (0 if r["_exato"] else 1,
                                num(r["COMMON_ORDER_RANK"]) or INF,
                                num(r["COMMON_TEST_RANK"]) or INF,
                                r["LOINC_NUM"]))
    return achados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("loinc_csv")
    ap.add_argument("lista_csv")
    ap.add_argument("saida_csv")
    ap.add_argument("--n", type=int, default=8)
    a = ap.parse_args()

    loinc = carregar_loinc(a.loinc_csv)
    with open(a.lista_csv, encoding="utf-8-sig", newline="") as f:
        exames = [r for r in csv.DictReader(f, delimiter=";") if r["tipo"] == "laboratorial" and r["busca_loinc"].strip()]

    cab = ["nome_exame", "busca_loinc", "candidato", "LOINC_NUM", "LONG_COMMON_NAME", "SYSTEM", "PROPERTY",
           "SCALE_TYP", "PanelType", "ORDER_OBS", "COMMON_ORDER_RANK", "COMMON_TEST_RANK", "escolher (s)"]
    sem_candidato = []
    with open(a.saida_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cab)
        for ex in exames:
            achados = candidatos(loinc, ex["busca_loinc"], ex["sistema_loinc"], ex["painel"])
            if not achados:
                sem_candidato.append(ex["nome_exame"])
                w.writerow([ex["nome_exame"], ex["busca_loinc"], 0] + [""] * (len(cab) - 3))
                continue
            for i, r in enumerate(achados[:a.n], 1):
                w.writerow([ex["nome_exame"], ex["busca_loinc"], i, r["LOINC_NUM"], r["LONG_COMMON_NAME"], r["SYSTEM"],
                            r.get("PROPERTY", ""), r.get("SCALE_TYP", ""), r.get("PanelType", ""), r.get("ORDER_OBS", ""),
                            r["COMMON_ORDER_RANK"], r["COMMON_TEST_RANK"], ""])
    print(f"{len(exames)} exames | sem nenhum candidato: {len(sem_candidato)}")
    for n in sem_candidato:
        print("  -", n)


if __name__ == "__main__":
    main()
