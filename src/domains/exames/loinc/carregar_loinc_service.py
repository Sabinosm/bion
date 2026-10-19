"""
Carga das tabelas de referencia do LOINC a partir dos arquivos baixados.

Unico ponto que escreve em loinc_termo / loinc_termo_traducao / loinc_painel_item
(mesmo espirito do AtualizacaoMedicamentosService: processo do sistema, sem
endpoint HTTP). Deve ser chamado por quem ja tem app_context aberto.

Regras (baseadas na inspecao dos arquivos reais):
- Tudo e lido pelo NOME do cabecalho, nunca pela posicao.
- Loinc.csv: carrega TODAS as linhas (todas as classes e status), em upsert por
  loinc_num -- reexecutar com uma versao nova atualiza sem apagar nada, entao as
  chaves que o catalogo ja usa continuam validas.
- pt-BR: so partes traduzidas. Valores '#N/A' (vistos em PROPERTY) viram NULL.
- PanelsAndForms.csv: so paineis laboratoriais; linhas-raiz (o proprio painel,
  ParentLoinc == Loinc) sao ignoradas. Tabela derivada: apagada e recarregada
  na mesma transacao.

Uso (dentro de um app_context):
    from src.domains.exames.loinc.carregar_loinc_service import executar
    executar("Loinc.csv", versao="2.xx", caminho_pt="ptBR11LinguisticVariant.csv",
             caminho_paineis="PanelsAndForms.csv")
"""

import csv
import logging
import sys

from sqlalchemy import and_, delete, func, insert

from src.models import db
from src.models.catalogos.loinc import LoincTermo, LoincTermoTraducao, LoincPainelItem
from src.models.catalogos.catalogo_exames import CatalogoExames

logger = logging.getLogger(__name__)
csv.field_size_limit(sys.maxsize)

TAMANHO_LOTE = 500
IDIOMA_PT = "pt-BR"
VAZIOS = {"", "#N/A", "N/A"}

COLUNAS_LOINC = ["LOINC_NUM", "COMPONENT", "PROPERTY", "TIME_ASPCT", "SYSTEM", "SCALE_TYP", "METHOD_TYP",
                 "CLASS", "CLASSTYPE", "STATUS", "ORDER_OBS", "PanelType", "LONG_COMMON_NAME",
                 "DisplayName", "SHORTNAME", "EXAMPLE_UCUM_UNITS", "COMMON_TEST_RANK", "COMMON_ORDER_RANK"]
COLUNAS_PT = ["LOINC_NUM", "COMPONENT", "PROPERTY", "TIME_ASPCT", "SYSTEM", "SCALE_TYP", "METHOD_TYP",
              "SHORTNAME", "RELATEDNAMES2"]
COLUNAS_PAINEIS = ["ParentLoinc", "Loinc", "SEQUENCE", "ObservationRequiredInPanel"]


def _txt(v):
    v = (v or "").strip()
    return None if v in VAZIOS else v


def _int(v):
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return None


def _ler_csv(caminho, obrigatorias):
    """Gera dicts por linha; falha cedo se faltar coluna obrigatoria."""
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        faltando = [c for c in obrigatorias if c not in (leitor.fieldnames or [])]
        if faltando:
            raise ValueError(f"{caminho}: colunas ausentes {faltando}")
        yield from leitor


def _lotes(itens, n=TAMANHO_LOTE):
    for i in range(0, len(itens), n):
        yield itens[i:i + n]


class CarregarLoincService:

    # ------------------------------------------------------------------
    def carregar(self, caminho_loinc: str, versao: str, caminho_pt: str | None = None,
                 caminho_paineis: str | None = None) -> dict:
        resumo = {}
        try:
            ids_todos, ids_lab = self._carregar_termos(caminho_loinc, versao, resumo)
            if caminho_pt:
                self._carregar_traducoes(caminho_pt, ids_todos, resumo)
            if caminho_paineis:
                self._carregar_paineis(caminho_paineis, ids_lab, ids_todos, resumo)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return resumo

    # ------------------------------------------------------------------
    def _carregar_termos(self, caminho, versao, resumo):
        ids_todos, ids_lab, lote = set(), set(), []
        total = 0
        for r in _ler_csv(caminho, COLUNAS_LOINC):
            loinc_num = _txt(r["LOINC_NUM"])
            if not loinc_num:
                continue
            classtype = _int(r["CLASSTYPE"])
            ids_todos.add(loinc_num)
            if classtype == 1:
                ids_lab.add(loinc_num)
            lote.append({
                "loinc_num": loinc_num,
                "componente": _txt(r["COMPONENT"]), "propriedade": _txt(r["PROPERTY"]),
                "tempo": _txt(r["TIME_ASPCT"]), "sistema": _txt(r["SYSTEM"]),
                "escala": _txt(r["SCALE_TYP"]), "metodo": _txt(r["METHOD_TYP"]),
                "classe": _txt(r["CLASS"]), "classtype": classtype, "status": _txt(r["STATUS"]),
                "order_obs": _txt(r["ORDER_OBS"]), "panel_type": _txt(r["PanelType"]),
                "nome_longo": _txt(r["LONG_COMMON_NAME"]), "nome_exibicao": _txt(r["DisplayName"]),
                "nome_curto": _txt(r["SHORTNAME"]), "unidade_exemplo_ucum": _txt(r["EXAMPLE_UCUM_UNITS"]),
                "rank_teste": _int(r["COMMON_TEST_RANK"]), "rank_pedido": _int(r["COMMON_ORDER_RANK"]),
                "versao_loinc": versao,
            })
            if len(lote) >= TAMANHO_LOTE:
                self._upsert(LoincTermo, lote, ["loinc_num"])
                db.session.commit()
                total += len(lote)
                lote = []
        if lote:
            self._upsert(LoincTermo, lote, ["loinc_num"])
            total += len(lote)
        resumo["termos"] = total
        resumo["termos_laboratoriais"] = len(ids_lab)
        return ids_todos, ids_lab

    def _carregar_traducoes(self, caminho, ids_todos, resumo):
        lote, total, sem_termo = [], 0, 0
        for r in _ler_csv(caminho, COLUNAS_PT):
            loinc_num = _txt(r["LOINC_NUM"])
            if loinc_num not in ids_todos:
                sem_termo += 1
                continue
            lote.append({
                "loinc_num": loinc_num, "idioma": IDIOMA_PT,
                "componente": _txt(r["COMPONENT"]), "propriedade": _txt(r["PROPERTY"]),
                "tempo": _txt(r["TIME_ASPCT"]), "sistema": _txt(r["SYSTEM"]),
                "escala": _txt(r["SCALE_TYP"]), "metodo": _txt(r["METHOD_TYP"]),
                "nome_curto": _txt(r["SHORTNAME"]), "nomes_relacionados": _txt(r["RELATEDNAMES2"]),
            })
            if len(lote) >= TAMANHO_LOTE:
                self._upsert(LoincTermoTraducao, lote, ["loinc_num", "idioma"])
                db.session.commit()
                total += len(lote)
                lote = []
        if lote:
            self._upsert(LoincTermoTraducao, lote, ["loinc_num", "idioma"])
            total += len(lote)
        resumo["traducoes_pt_br"] = total
        resumo["traducoes_ignoradas_sem_termo"] = sem_termo

    def _carregar_paineis(self, caminho, ids_lab, ids_todos, resumo):
        itens, filho_desconhecido = [], 0
        for r in _ler_csv(caminho, COLUNAS_PAINEIS):
            pai, filho = _txt(r["ParentLoinc"]), _txt(r["Loinc"])
            if not pai or not filho or pai == filho:  # linha-raiz: o proprio painel
                continue
            if pai not in ids_lab:
                continue
            if filho not in ids_todos:
                filho_desconhecido += 1
                continue
            itens.append({"painel_loinc": pai, "filho_loinc": filho,
                          "sequencia": _int(r["SEQUENCE"]),
                          "obrigatoriedade": _txt(r["ObservationRequiredInPanel"])})
        db.session.execute(delete(LoincPainelItem.__table__))
        for lote in _lotes(itens):
            db.session.execute(insert(LoincPainelItem.__table__), lote)
        resumo["itens_de_painel"] = len(itens)
        resumo["itens_ignorados_filho_desconhecido"] = filho_desconhecido

    # ------------------------------------------------------------------
    @staticmethod
    def _upsert(model, linhas, chave):
        tabela = model.__table__
        dialeto = db.session.get_bind().dialect.name
        if dialeto == "mysql":
            from sqlalchemy.dialects.mysql import insert as ins
            stmt = ins(tabela).values(linhas)
            stmt = stmt.on_duplicate_key_update(
                **{c.name: stmt.inserted[c.name] for c in tabela.columns if c.name not in chave})
        elif dialeto == "sqlite":  # usado nos testes
            from sqlalchemy.dialects.sqlite import insert as ins
            stmt = ins(tabela).values(linhas)
            stmt = stmt.on_conflict_do_update(
                index_elements=chave,
                set_={c.name: stmt.excluded[c.name] for c in tabela.columns if c.name not in chave})
        else:
            raise NotImplementedError(f"upsert nao implementado para {dialeto}")
        db.session.execute(stmt)

    # ------------------------------------------------------------------
    # Semente para curadoria
    # ------------------------------------------------------------------
    def exportar_candidatos(self, caminho_csv: str) -> int:
        """CSV (';', utf-8 com BOM, abre no Excel) com os laboratoriais ACTIVE que tem
        COMMON_ORDER_RANK, para a curadoria preencher nome_exame, material, jejum etc.
        Rank e dos EUA: a lista brasileira precisa ser revista (juntar variantes,
        tirar o que nao se pede aqui, incluir o que falta)."""
        n_itens = (
            db.session.query(LoincPainelItem.painel_loinc.label("painel"),
                             func.count(LoincPainelItem.id).label("n"))
            .group_by(LoincPainelItem.painel_loinc).subquery()
        )
        linhas = (
            db.session.query(LoincTermo, LoincTermoTraducao, n_itens.c.n)
            .outerjoin(LoincTermoTraducao, and_(LoincTermoTraducao.loinc_num == LoincTermo.loinc_num,
                                                LoincTermoTraducao.idioma == IDIOMA_PT))
            .outerjoin(n_itens, n_itens.c.painel == LoincTermo.loinc_num)
            .filter(LoincTermo.classtype == 1, LoincTermo.status == "ACTIVE", LoincTermo.rank_pedido > 0)
            .order_by(LoincTermo.rank_pedido)
            .all()
        )
        ja = {c for (c,) in db.session.query(CatalogoExames.codigo_loinc)
              .filter(CatalogoExames.codigo_loinc.isnot(None))}
        cab = ["rank_pedido", "codigo_loinc", "tipo_loinc", "nome_en", "amostra_en", "componente_pt",
               "sistema_pt", "itens_no_painel", "ja_no_catalogo",
               "incluir (s/n)", "nome_exame", "tipo", "material", "jejum_horas", "observacoes"]
        with open(caminho_csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(cab)
            for t, tr, n in linhas:
                w.writerow([t.rank_pedido, t.loinc_num, t.panel_type or "", t.nome_exibicao or "",
                            t.sistema or "", (tr.componente if tr else "") or "",
                            (tr.sistema if tr else "") or "", n or "",
                            "s" if t.loinc_num in ja else "", "", "", "laboratorial", "", "", ""])
        return len(linhas)


def executar(caminho_loinc, versao, caminho_pt=None, caminho_paineis=None) -> dict:
    """Ponto de entrada para quem ja tem app_context aberto."""
    resumo = CarregarLoincService().carregar(caminho_loinc, versao, caminho_pt, caminho_paineis)
    for k, v in resumo.items():
        logger.info("LOINC %s: %s", k, v)
    return resumo
