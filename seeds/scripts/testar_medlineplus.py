#!/usr/bin/env python3
"""Chama o MedlinePlus Connect para alguns códigos LOINC e salva a resposta CRUA,
para vermos o formato real antes de modelar a tabela de conteúdo.

Uso:
    python scripts/exames/testar_medlineplus.py 2345-7 718-7 --lang en
    python scripts/exames/testar_medlineplus.py 2345-7 --dry-run        # só mostra a URL

O NLM limita a 100 requisições/min por IP; o script espera 1 s entre chamadas.
"""
import argparse
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://connect.medlineplus.gov/service"
OID_LOINC = "2.16.840.1.113883.6.1"  # OID do LOINC que conheço; confirme na doc do NLM


def url_para(codigo, lang):
    q = {
        "mainSearchCriteria.v.cs": OID_LOINC,
        "mainSearchCriteria.v.c": codigo,
        "knowledgeResponseType": "application/json",
        "informationRecipient.languageCode.c": lang,
    }
    return f"{BASE}?{urllib.parse.urlencode(q)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codigos", nargs="+")
    ap.add_argument("--lang", default="en", choices=["en", "es"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    for cod in a.codigos:
        url = url_para(cod, a.lang)
        print(f"\n[{cod}] {url}")
        if a.dry_run:
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bion-catalogo-exames-teste"})
            with urllib.request.urlopen(req, timeout=30) as r:
                corpo = r.read().decode("utf-8", errors="replace")
                print("HTTP", r.status, "| bytes:", len(corpo))
        except urllib.error.HTTPError as e:
            print("HTTP", e.code, e.reason)
            continue
        except Exception as e:  # rede, timeout...
            print("erro:", e)
            continue
        arq = pathlib.Path(f"medlineplus_{cod}_{a.lang}.json")
        arq.write_text(corpo, encoding="utf-8")
        print("salvo em", arq, "\n", corpo[:600])
        time.sleep(1)


if __name__ == "__main__":
    main()
