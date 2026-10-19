#!/usr/bin/env python3
"""
Parser da resposta JSON do MedlinePlus Connect (busca por código LOINC).

Formato observado (código 2345-7): feed.entry[] com 2 entradas
  - um TÓPICO geral ("Blood Glucose")
  - a página do EXAME ("Blood Glucose Test"; a URL contém /lab-tests/)
Cada entrada traz title, link[].href, id, summary (HTML) e updated.

Decisões:
- `entry` e `link` podem vir como objeto único em vez de lista (conversão XML->JSON): normalizamos.
- `updated` é o horário da requisição, não a data do conteúdo: não é usado.
- O HTML do summary vira seções {chave, titulo, texto}; links, atributos e a seção
  "References" são descartados; a linha de atribuição (NLMattribution) é guardada à parte.
- Só nas páginas de exame as seções recebem `chave` (o_que_e, para_que_serve...),
  a partir dos títulos em inglês.

Uso para inspecionar um JSON salvo:
    python medlineplus_parser.py medlineplus_2345-7_en.json
"""
import hashlib
import json
import sys
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# (trecho do título em minúsculas, chave) -- a ordem importa: "used for" antes de "what is"
CHAVES_SECAO = [
    ("used for", "para_que_serve"),
    ("why do i need", "por_que_pedir"),
    ("why would i need", "por_que_pedir"),
    ("what happens", "como_e_feito"),
    ("prepare", "preparo"),
    ("risk", "riscos"),
    ("results mean", "resultados"),
    ("anything else", "outras_informacoes"),
]
TITULOS_IGNORADOS = ("references", "referências", "referencias")


def _norm(texto: str) -> str:
    return " ".join((texto or "").split())


class _ConversorHtml(HTMLParser):
    """HTML -> seções em texto simples (listas viram '- ' com recuo por nível)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.secoes = []
        self.atribuicao = None
        self._titulo = None
        self._linhas = []
        self._buf = []
        self._prof = 0
        self._bullet = False
        self._em_titulo = False
        self._buf_titulo = []
        self._em_atrib = False
        self._buf_atrib = []

    # --- helpers
    def _flush(self):
        texto = _norm("".join(self._buf))
        self._buf = []
        if not texto:
            return
        if self._prof > 0:
            if self._bullet:
                linha = "  " * (self._prof - 1) + "- " + texto
                self._bullet = False
            else:
                linha = "  " * self._prof + texto  # continuação dentro do item
        else:
            linha = texto
        self._linhas.append(linha)

    def _fechar_secao(self):
        self._flush()
        if self._titulo is not None or self._linhas:
            self.secoes.append({"titulo": self._titulo, "texto": "\n".join(self._linhas)})
        self._linhas = []

    # --- eventos
    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4"):
            self._flush()
            self._em_titulo, self._buf_titulo = True, []
        elif tag == "p":
            self._flush()
            if "NLMattribution" in (dict(attrs).get("class") or ""):
                self._em_atrib, self._buf_atrib = True, []
        elif tag == "br":
            self._flush()
        elif tag in ("ul", "ol"):
            self._flush()
            self._prof += 1
        elif tag == "li":
            self._flush()
            self._bullet = True

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4"):
            self._em_titulo = False
            titulo = _norm("".join(self._buf_titulo))
            self._fechar_secao()
            self._titulo = titulo
        elif tag == "p":
            if self._em_atrib:
                self.atribuicao = _norm("".join(self._buf_atrib)) or None
                self._em_atrib = False
            else:
                self._flush()
        elif tag in ("ul", "ol"):
            self._flush()
            self._prof = max(0, self._prof - 1)
        elif tag == "li":
            self._flush()
            self._bullet = False

    def handle_data(self, data):
        if self._em_titulo:
            self._buf_titulo.append(data)
        elif self._em_atrib:
            self._buf_atrib.append(data)
        else:
            self._buf.append(data)

    def concluir(self):
        self._fechar_secao()
        return self.secoes


def html_para_secoes(html: str):
    """Retorna (secoes, atribuicao). Descarta a seção de referências."""
    conv = _ConversorHtml()
    conv.feed(html or "")
    conv.close()
    secoes = [s for s in conv.concluir()
              if not (s["titulo"] or "").strip().lower().startswith(TITULOS_IGNORADOS)
              and (s["titulo"] or s["texto"])]
    return secoes, conv.atribuicao


def dividir_virgulas(texto: str):
    """Divide por vírgula fora de parênteses: 'a (x, y), b' -> ['a (x, y)', 'b']."""
    partes, atual, nivel = [], [], 0
    for ch in texto:
        if ch == "(":
            nivel += 1
        elif ch == ")":
            nivel = max(0, nivel - 1)
        if ch == "," and nivel == 0:
            partes.append("".join(atual))
            atual = []
        else:
            atual.append(ch)
    partes.append("".join(atual))
    return [_norm(p) for p in partes if _norm(p)]


def limpar_url(url: str) -> str:
    """Remove parâmetros utm_* (rastreamento do próprio serviço)."""
    if not url:
        return ""
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def _lista(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def _valor(x):
    return x.get("_value") if isinstance(x, dict) else x


def _chave_da_secao(titulo: str):
    t = (titulo or "").lower()
    for trecho, chave in CHAVES_SECAO:
        if trecho in t:
            return chave
    if t.startswith("what is"):
        return "o_que_e"
    return None


def _outros_nomes(secoes):
    for s in secoes:
        for linha in s["texto"].split("\n"):
            if linha.lower().startswith("other names:"):
                return dividir_virgulas(linha.split(":", 1)[1])
    return []


def interpretar_resposta(payload: dict) -> list:
    """Lista de entradas normalizadas (vazia se o serviço não devolveu conteúdo)."""
    feed = (payload or {}).get("feed") or {}
    resultado = []
    for e in _lista(feed.get("entry")):
        url = ""
        for link in _lista(e.get("link")):
            if isinstance(link, dict) and link.get("href") and link.get("rel") in (None, "alternate"):
                url = limpar_url(link["href"])
                break
        html = _valor(e.get("summary")) or ""
        tipo = "exame" if "/lab-tests/" in url else "topico"
        secoes, atribuicao = html_para_secoes(html)
        for s in secoes:
            s["chave"] = _chave_da_secao(s["titulo"]) if tipo == "exame" else None
        texto_plano = "\n\n".join((f"{s['titulo']}\n{s['texto']}" if s["titulo"] else s["texto"]) for s in secoes)
        resultado.append({
            "titulo": _norm(_valor(e.get("title")) or ""),
            "url": url,
            "url_hash": hashlib.sha1(url.encode("utf-8")).hexdigest(),
            "tipo": tipo,
            "secoes": secoes,
            "outros_nomes": _outros_nomes(secoes),
            "atribuicao": atribuicao,
            "texto_plano": texto_plano,
            "hash_conteudo": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        })
    return resultado


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    with open(sys.argv[1], encoding="utf-8") as f:
        entradas = interpretar_resposta(json.load(f))
    print(f"{len(entradas)} entrada(s)")
    for e in entradas:
        print(f"\n[{e['tipo']}] {e['titulo']}  {e['url']}")
        print("  outros nomes:", e["outros_nomes"])
        print("  atribuição:", e["atribuicao"])
        for s in e["secoes"]:
            print(f"  - ({s['chave']}) {s['titulo']}: {len(s['texto'])} caracteres")
