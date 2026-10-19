"""Normalização de nomes de exame para busca e para evitar duplicidade
(sem acento, minúsculo, espaços colapsados). Não confundir com a normalização de
princípio ativo do domínio de medicamentos, que também remove prefixos de sal."""

import re
import unicodedata


def normalizar_texto(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto or "")
    s = s.encode("ascii", "ignore").decode("ascii").lower().strip()
    return re.sub(r"\s+", " ", s)


def montar_busca_normalizada(nome: str, nome_en: str | None = None, sinonimos=None) -> str:
    """Texto único para a busca do médico: nome (pt), nome em inglês e sinônimos, normalizados e
    sem repetição, separados por ' | '. Gravado em catalogo_exames.busca_normalizada."""
    partes, vistos = [], set()
    for t in [nome, nome_en, *(sinonimos or [])]:
        n = normalizar_texto(t or "")
        if n and n not in vistos:
            vistos.add(n)
            partes.append(n)
    return " | ".join(partes)
