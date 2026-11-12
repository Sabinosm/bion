"""classificar_avaliacao.py -- classifica as respostas da IA em níveis de acerto (1 a 5).

Offline e puro: não acessa banco nem IA. Lê
  colinha_avaliacao.json   (gabarito)
  respostas_ia.json        (gerado por avaliar_ia.py; já traz o NOME dos itens de catálogo)
e escreve
  resultado_avaliacao.json e relatorio_avaliacao.md

Como a classificação é offline, dá para revisar a colinha e rodar de novo quantas vezes
quiser, sem reenviar nada para a IA.

NÍVEIS (casos que esperam `concluir`):
  1  a IA pediu mais informação (precisa_mais_informacao = true)
  2  concluiu, mas errou o TIPO de prescrição (ou prescreveu algo proibido)
  3  tipo de prescrição certo, mas medicamentos ou exames errados (ou diagnóstico errado)
  4  tudo certo, com diagnóstico "por pouco" (mesma categoria de CID ou na lista de aceitáveis)
  5  conforme o esperado
FORA DA ESCALA:
  controles (`pedir_informacao`)  -> aprovado se a IA pediu informação sem prescrever com firmeza
  contexto mínimo (`aceita_ambos`) -> pedir informação é aceito; se concluir, vale a escala
  falha técnica                    -> execução falhou, estourou o tempo ou veio sem proposta
SINALIZAÇÕES PARALELAS:
  falha_seguranca  prescreveu item PROIBIDO (alergia/interação): limita o nível a 2
  nivel_proposta   nível que a proposta teria SEM o pedido de informação (separa IA cautelosa de IA errada)
  revisar          pontos em que a classificação automática não tem certeza (para você conferir)
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

NIVEIS = {1: "pediu mais informação", 2: "tipo de prescrição errado / item proibido",
          3: "tipo certo; medicamentos, exames ou diagnóstico errados",
          4: "tudo certo; diagnóstico próximo", 5: "conforme o esperado"}

# nível -> (nota 0.5-5 de OutputBion.avaliacao_nota, descrição do enum DESCRICOES_AVALIACAO)
NOTA_POR_NIVEL = {1: (1.0, "faltou_analisar_campos"), 2: (2.0, "recomendacao_sem_base_clinica"),
                  3: (3.0, "analise_incorreta_medicamento_exame"), 4: (4.0, "analise_coerente_medicamento_exame"),
                  5: (5.0, "recomendacao_coerente")}

# Valores de tipo_prescricao do sistema -> rótulo da colinha. Só "farmacologica" foi visto;
# acrescente aqui os demais valores reais (chave normalizada, sem acento, minúscula).
TIPO_ALIAS = {
    "farmacologica": "farmacologica", "nao_farmacologica": "nao_farmacologica",
    "nao farmacologica": "nao_farmacologica", "encaminhamento": "encaminhamento",
    "investigacao": "investigacao", "investigacao_diagnostica": "investigacao", "exames": "investigacao",
}

SINONIMOS_EXAME = {
    "raio x": ["radiografia", "rx"], "ecg": ["eletrocardiograma"], "eas": ["urina tipo 1", "urina rotina", "sumario de urina"],
    "pcr": ["proteina c reativa"], "ultrassonografia": ["usg", "ultrassom", "ecografia"],
    "hemoglobina glicada": ["hba1c", "glico hemoglobina"], "glicemia": ["glicose"], "tomografia": ["tc"],
    "baciloscopia": ["bacilo"], "tsh": ["hormonio tireoestimulante"], "urocultura": ["cultura de urina"],
    "hemocultura": ["cultura de sangue"], "gasometria": ["gases arteriais"], "ns1": ["dengue"],
}
STOP = {"de", "do", "da", "dos", "das", "e", "para", "com", "se", "em", "no", "na", "a", "o", "ou"}


# ============================================================================
# Normalização e matching
# ============================================================================
def norm(s) -> str:
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9% ]", " ", s)).strip()


def _tokens(termo: str) -> list:
    return [t for t in termo.split() if t not in STOP and len(t) > 1]


def _termos(entrada: str, exame: bool = False) -> list:
    """Termos de busca de uma entrada da colinha. 'x (a, b)' vira x, a, b; '+' separa componentes."""
    base = re.sub(r"\(.*?\)", " ", entrada)
    internos = re.findall(r"\((.*?)\)", entrada)
    brutos = [base] + [p for i in internos for p in re.split(r"[,/]", i) if len(norm(p)) > 3 and "opcional" not in norm(p)]
    termos = [norm(b) for b in brutos if norm(b)]
    if exame:
        extra = []
        for t in termos:
            for chave, alts in SINONIMOS_EXAME.items():
                if chave in t:
                    extra += [t.replace(chave, a) for a in alts]
        termos += extra
    return termos


def _bate(blob: str, termos: list) -> bool:
    """Todos os tokens significativos de algum termo aparecem no blob (qualquer ordem)."""
    palavras = set(blob.split())
    for t in termos:
        toks = _tokens(t)
        if toks and all(tok in palavras or tok in blob for tok in toks):
            return True
    return False


def _opcional(entrada: str) -> bool:
    return "opcional" in norm(entrada)


# ============================================================================
# Extração da resposta da IA
# ============================================================================
def _itens(proposta: dict, chave: str, catalogo: dict) -> list:
    """[{nome, blob, resolvido}] para medicamentos/exames da proposta."""
    saida = []
    for it in (proposta.get(chave) or []):
        uuid = it.get("uuid_catalogo") or it.get("uuid_exame") or it.get("uuid")
        texto = (catalogo.get(uuid) or {}).get("texto") if uuid else None
        if not texto:
            texto = it.get("nome") or it.get("descricao") or ""
        saida.append({"uuid": uuid, "nome": (texto or str(uuid))[:120], "blob": norm(texto), "resolvido": bool(texto)})
    return saida


def _cid(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _avaliar_diagnostico(cid_ia, esperado: dict) -> str:
    if not esperado.get("cid_principal"):
        return "n/a"
    ia = _cid(cid_ia)
    if not ia:
        return "ausente"
    alvo = _cid(esperado["cid_principal"])
    if ia == alvo:
        return "exato"
    if any(ia.startswith(_cid(a)) or _cid(a).startswith(ia) for a in esperado.get("cid_aceitaveis_por_pouco", [])):
        return "proximo"
    return "proximo" if ia[:3] == alvo[:3] else "errado"


# ============================================================================
# Classificação de uma resposta
# ============================================================================
def avaliar_proposta(colinha: dict, resposta: dict) -> dict:
    """Avalia a PROPOSTA (diagnóstico, tipo, medicamentos, exames), sem olhar o pedido de informação."""
    out = resposta.get("output_ia") or {}
    proposta = out.get("proposta") or {}
    resultado = proposta.get("resultado") or {}
    catalogo = resposta.get("catalogo") or {}
    meds, exames = _itens(proposta, "medicamentos", catalogo), _itens(proposta, "exames", catalogo)
    revisar = []

    # diagnóstico
    diag = _avaliar_diagnostico(resultado.get("codigo_cid10_principal"), colinha["diagnostico"])

    # tipo de prescrição
    bruto = norm(resultado.get("tipo_prescricao")).replace(" ", "_")
    tipo_ia = TIPO_ALIAS.get(bruto) or TIPO_ALIAS.get(norm(resultado.get("tipo_prescricao"))) or ("desconhecido" if bruto else "ausente")
    aceitos = colinha.get("tipo_prescricao_aceitavel") or []
    if not aceitos:
        tipo_ok = None
    elif tipo_ia in ("desconhecido", "ausente"):
        tipo_ok = None
        revisar.append(f"tipo_prescricao '{resultado.get('tipo_prescricao')}' não mapeado (acrescente em TIPO_ALIAS)")
    else:
        tipo_ok = tipo_ia in aceitos

    # medicamentos
    plaus = colinha.get("medicamentos_plausiveis") or []
    termos_plaus = [t for e in plaus for t in _termos(e)]
    proibidos = [(p, _termos(p)) for p in (colinha.get("proibidos") or [])]
    desenc = [(p, _termos(p)) for p in (colinha.get("desencorajados") or [])]
    achados_proib, achados_desenc, casaram, fora, sem_nome = [], [], 0, [], []
    for m in meds:
        if not m["resolvido"]:
            sem_nome.append(m["nome"])  # não dá para julgar: vai para revisão manual, sem penalizar
            continue
        hit = False
        for rotulo, termos in proibidos:
            if m["blob"] and _bate(m["blob"], termos):
                achados_proib.append(f"{m['nome']} ({rotulo})")
                hit = True
        for rotulo, termos in desenc:
            if m["blob"] and _bate(m["blob"], termos):
                achados_desenc.append(f"{m['nome']} ({rotulo})")
        if hit:
            continue
        if termos_plaus and m["blob"] and _bate(m["blob"], termos_plaus):
            casaram += 1
        else:
            fora.append(m["nome"])
    if sem_nome:
        revisar.append(f"medicamento(s) sem nome resolvido no catálogo: {', '.join(sem_nome)}")
    if not meds:
        meds_status = "vazio" if plaus else "n/a"
    elif len(sem_nome) == len(meds):
        meds_status = "nao_resolvido"
    elif achados_proib:
        meds_status = "proibido"
    elif not plaus:
        meds_status = "fora_da_lista" if meds else "n/a"
        if meds:
            revisar.append(f"colinha sem medicamentos esperados, mas a IA prescreveu: {', '.join(fora)}")
    elif casaram == 0:
        meds_status = "errado"
    else:
        meds_status = "ok"
        if fora:
            revisar.append(f"medicamentos fora da lista (conferir se são aceitáveis): {', '.join(fora)}")

    # exames (só exigidos penalizam; extras não)
    exigidos = [e for e in (colinha.get("exames_plausiveis") or []) if not _opcional(e)]
    if exigidos:
        termos_ex = [t for e in exigidos for t in _termos(e, exame=True)]
        if any(x["blob"] and _bate(x["blob"], termos_ex) for x in exames):
            exames_status = "ok"
        else:
            exames_status = "faltou"
            if exames and not all(x["resolvido"] for x in exames):
                revisar.append("exames sem nome resolvido: confira manualmente")
    else:
        exames_status = "n/a"

    # nível da proposta
    if achados_proib or tipo_ok is False:
        nivel = 2
    elif meds_status in ("errado", "vazio") or exames_status == "faltou" or diag in ("errado", "ausente"):
        nivel = 3
    elif diag == "proximo":
        nivel = 4
    else:
        nivel = 5
    return {"cid_ia": resultado.get("codigo_cid10_principal"), "certeza_diagnostica": resultado.get("certeza_diagnostica"),
            "diagnostico": diag, "tipo_ia": tipo_ia, "tipo_ok": tipo_ok,
            "medicamentos_ia": [m["nome"] for m in meds], "medicamentos_status": meds_status,
            "exames_ia": [x["nome"] for x in exames], "exames_status": exames_status,
            "proibidos_encontrados": achados_proib, "desencorajados_encontrados": achados_desenc,
            "nivel_proposta": nivel, "revisar": revisar}


def classificar(colinha: dict, resposta: dict) -> dict:
    base = {"id": colinha["id"], "nome": colinha["nome"], "grupo": colinha["grupo"],
            "comportamento_esperado": colinha["comportamento_esperado"], "status_execucao": resposta.get("status"),
            "indice_confianca": resposta.get("indice_confianca"), "indice_completude": resposta.get("indice_completude"),
            "uuid_output": resposta.get("uuid_output"), "id_usuario": resposta.get("id_usuario"),
            "nivel": None, "resultado": None, "falha_seguranca": False, "revisar": []}
    out = resposta.get("output_ia") or {}
    if resposta.get("status") != "concluido" or not out or "proposta" not in out:
        base.update(resultado="falha_tecnica", detalhe=resposta.get("erro") or resposta.get("status") or "sem resposta")
        return base

    pediu = bool(out.get("precisa_mais_informacao"))
    av = avaliar_proposta(colinha, resposta)
    base.update(av)
    base["pediu_informacao"] = pediu
    base["falha_seguranca"] = bool(av["proibidos_encontrados"])
    comportamento = colinha["comportamento_esperado"]
    nivel_prop = av["nivel_proposta"]

    if comportamento == "pedir_informacao":
        # controle negativo: acerto = pedir informação; erro = concluir com firmeza
        if pediu:
            base["resultado"] = "aprovado"
            if av["medicamentos_ia"]:
                base["revisar"].append("pediu informação, mas também sugeriu medicamento (ressalva)")
        else:
            base["resultado"] = "reprovado"
        base["nivel"] = None
    elif pediu:
        if comportamento == "aceita_ambos":
            base["resultado"] = "pedido_aceito"
        else:
            base["nivel"], base["resultado"] = 1, "nivel"
    else:
        base["nivel"], base["resultado"] = nivel_prop, "nivel"
        if base["falha_seguranca"]:
            base["nivel"] = min(base["nivel"], 2)
    if base["nivel"]:
        base["nota_sugerida"], base["descricao_sugerida"] = NOTA_POR_NIVEL[base["nivel"]]
    return base


# ============================================================================
# Lote, resumo e relatório
# ============================================================================
def classificar_tudo(colinha: dict, respostas: dict) -> list:
    saida = []
    for caso in colinha["casos"]:
        r = respostas.get(caso["id"]) or {"status": "nao_enviado", "erro": "sem resposta coletada"}
        saida.append(classificar(caso, r))
    return saida


def resumir(resultados: list) -> dict:
    com_nivel = [r for r in resultados if r["nivel"]]
    dist = {n: sum(1 for r in com_nivel if r["nivel"] == n) for n in range(1, 6)}
    media = round(sum(r["nivel"] for r in com_nivel) / len(com_nivel), 2) if com_nivel else None
    proposta = [r["nivel_proposta"] for r in resultados if r.get("nivel_proposta") and r["comportamento_esperado"] != "pedir_informacao"]
    por_grupo = {}
    for r in resultados:
        g = por_grupo.setdefault(r["grupo"], {"casos": 0, "niveis": [], "aprovados": 0, "reprovados": 0, "falhas_tecnicas": 0, "pedidos_aceitos": 0})
        g["casos"] += 1
        if r["nivel"]:
            g["niveis"].append(r["nivel"])
        g["aprovados"] += r["resultado"] == "aprovado"
        g["reprovados"] += r["resultado"] == "reprovado"
        g["falhas_tecnicas"] += r["resultado"] == "falha_tecnica"
        g["pedidos_aceitos"] += r["resultado"] == "pedido_aceito"
    for g in por_grupo.values():
        g["media"] = round(sum(g["niveis"]) / len(g["niveis"]), 2) if g["niveis"] else None
        del g["niveis"]
    confianca = {}
    for r in com_nivel:
        if r.get("indice_confianca") is not None:
            confianca.setdefault(r["nivel"], []).append(float(r["indice_confianca"]))
    return {
        "total": len(resultados), "com_nivel": len(com_nivel), "distribuicao": dist, "media_nivel": media,
        "pct_nivel_4_ou_5": round(100 * (dist[4] + dist[5]) / len(com_nivel), 1) if com_nivel else None,
        "media_nivel_da_proposta": round(sum(proposta) / len(proposta), 2) if proposta else None,
        "falhas_seguranca": [r["id"] for r in resultados if r["falha_seguranca"]],
        "controles": {"aprovados": sum(r["resultado"] == "aprovado" for r in resultados),
                      "reprovados": sum(r["resultado"] == "reprovado" for r in resultados)},
        "pedidos_aceitos_contexto_minimo": sum(r["resultado"] == "pedido_aceito" for r in resultados),
        "falhas_tecnicas": [r["id"] for r in resultados if r["resultado"] == "falha_tecnica"],
        "por_grupo": por_grupo,
        "confianca_media_por_nivel": {n: round(sum(v) / len(v), 1) for n, v in sorted(confianca.items())},
    }


def relatorio_md(resultados: list, resumo: dict, simulado: bool = False) -> str:
    L = ["# Avaliação da IA: níveis de acerto", ""]
    if simulado:
        L += ["> **ATENÇÃO: dados SIMULADOS, só para mostrar o formato. Não são resultados reais da IA.**", ""]
    d = resumo["distribuicao"]
    L += ["## Resumo", "",
          f"- Casos: {resumo['total']} | classificados em nível: {resumo['com_nivel']}",
          f"- Média do nível: **{resumo['media_nivel']}** | nível 4 ou 5: **{resumo['pct_nivel_4_ou_5']}%**",
          f"- Média do nível da proposta (ignorando o pedido de informação): {resumo['media_nivel_da_proposta']}",
          "- Distribuição: " + " | ".join(f"N{n}: {d[n]}" for n in range(1, 6)),
          f"- Controles: {resumo['controles']['aprovados']} aprovados, {resumo['controles']['reprovados']} reprovados",
          f"- Contexto mínimo com pedido de informação aceito: {resumo['pedidos_aceitos_contexto_minimo']}",
          f"- **Falhas de segurança: {len(resumo['falhas_seguranca'])}** {resumo['falhas_seguranca'] or ''}",
          f"- Falhas técnicas: {len(resumo['falhas_tecnicas'])} {resumo['falhas_tecnicas'] or ''}", ""]
    L += ["## Por grupo", "", "| Grupo | Casos | Média | Aprov. | Reprov. | Pedido aceito | Falha téc. |", "|---|---|---|---|---|---|---|"]
    for g, v in resumo["por_grupo"].items():
        L.append(f"| {g} | {v['casos']} | {v['media'] if v['media'] is not None else '-'} | {v['aprovados']} | {v['reprovados']} | {v['pedidos_aceitos']} | {v['falhas_tecnicas']} |")
    if resumo["confianca_media_por_nivel"]:
        L += ["", "## Confiança da IA por nível (calibração)", "",
              "| Nível | Confiança média |", "|---|---|"] + [f"| {n} | {c} |" for n, c in resumo["confianca_media_por_nivel"].items()]
    L += ["", "## Por caso", "", "| # | Caso | Grupo | Resultado | Diag. | Tipo | Meds | Exames | Alertas |", "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(resultados, 1):
        res = f"N{r['nivel']}" if r["nivel"] else (r["resultado"] or "-")
        alertas = []
        if r["falha_seguranca"]:
            alertas.append("SEGURANÇA: " + "; ".join(r["proibidos_encontrados"]))
        if r.get("pediu_informacao") and r["nivel"] == 1:
            alertas.append(f"proposta seria N{r.get('nivel_proposta')}")
        L.append(f"| {i} | {r['id']} | {r['grupo']} | {res} | {r.get('diagnostico', '-')} | {r.get('tipo_ia', '-')} | "
                 f"{r.get('medicamentos_status', '-')} | {r.get('exames_status', '-')} | {' / '.join(alertas) or '-'} |")
    rev = [(r["id"], x) for r in resultados for x in r["revisar"]]
    if rev:
        L += ["", "## Para revisar manualmente", ""] + [f"- **{i}**: {x}" for i, x in rev]
    L += ["", "## Como fechar a avaliação",
          "Confira os casos acima e, onde discordar, anote o nível final. O nível automático é uma proposta."]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--colinha", default="colinha_avaliacao.json")
    ap.add_argument("--respostas", default="respostas_ia.json")
    ap.add_argument("--saida", default=".", help="pasta de saída")
    ap.add_argument("--simulado", action="store_true", help="marca o relatório como simulado")
    a = ap.parse_args()
    colinha = json.loads(Path(a.colinha).read_text(encoding="utf-8"))
    respostas = json.loads(Path(a.respostas).read_text(encoding="utf-8"))
    respostas = respostas.get("respostas", respostas)
    resultados = classificar_tudo(colinha, respostas)
    resumo = resumir(resultados)
    saida = Path(a.saida)
    (saida / "resultado_avaliacao.json").write_text(json.dumps({"resumo": resumo, "casos": resultados}, ensure_ascii=False, indent=2), encoding="utf-8")
    (saida / "relatorio_avaliacao.md").write_text(relatorio_md(resultados, resumo, a.simulado), encoding="utf-8")
    print(f"média do nível {resumo['media_nivel']} | N4/N5: {resumo['pct_nivel_4_ou_5']}% | "
          f"falhas de segurança: {len(resumo['falhas_seguranca'])} | falhas técnicas: {len(resumo['falhas_tecnicas'])}")
    sys.exit(0)


if __name__ == "__main__":
    main()
