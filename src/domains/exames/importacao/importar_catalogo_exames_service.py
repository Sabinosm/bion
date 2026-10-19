"""
Importa a lista curada de exames (CSV) para catalogo_exames.

Fluxo: gerar/editar seeds/exames/exames_brasil_candidatos.csv (preencher codigo_loinc depois de
rodar scripts/exames/sugerir_loinc.py) -> executar(..., dry_run=True) para conferir -> executar().

Regras:
- Chave natural: nome normalizado (sem acento/minúsculo). Linhas antigas sem nome_normalizado são
  "adotadas" quando o nome coincide. Renomear um exame no CSV cria uma linha nova (a antiga deve ser
  desativada à mão).
- Atualiza: nome, nome em inglês, tipo, material (pt/en), sinônimos, codigo_loinc e busca_normalizada.
  NÃO toca em jejum_horas, observacoes nem codigo_tuss (curados em outro lugar).
- `ativo` só vale na criação; em linhas existentes só é sobrescrito com sobrescrever_ativo=True.
- Valida tudo antes de gravar: com qualquer erro, nada é gravado (a menos que ignorar_erros=True).
- codigo_loinc exige que o termo exista em loinc_termo (rode a carga do LOINC antes), que o exame seja
  laboratorial e que o termo não esteja DEPRECATED; termos não ACTIVE geram aviso.

Uso (dentro de um app_context):
    from src.domains.exames.importacao.importar_catalogo_exames_service import executar
    executar("seeds/exames/exames_brasil_candidatos.csv", dry_run=True)
"""

import csv
import logging
import re

from sqlalchemy import func

from src.models import db
from src.models.catalogos.catalogo_exames import CatalogoExames
from src.models.catalogos.loinc import LoincTermo
from ..normalizacao import montar_busca_normalizada, normalizar_texto

logger = logging.getLogger(__name__)

COLUNAS_OBRIGATORIAS = ["nome_exame", "nome_exame_en", "tipo", "material", "material_en",
                        "sinonimos_busca", "codigo_loinc", "ativo"]
TIPOS = {"laboratorial", "imagem", "funcional", "outro"}
RE_LOINC = re.compile(r"^\d{1,7}-\d$")
SIM = {"s", "sim", "1", "true", "x", ""}          # vazio = padrão do modelo (ativo)
NAO = {"n", "nao", "não", "0", "false"}
CAMPOS = ("nome_exame", "nome_exame_en", "tipo", "material", "material_en", "sinonimos_busca_json", "codigo_loinc",
          "busca_normalizada")


def _txt(v):
    v = " ".join((v or "").split())
    return v or None


class ImportarCatalogoExamesService:

    def importar(self, caminho_csv: str, dry_run: bool = False, sobrescrever_ativo: bool = False,
                 ignorar_erros: bool = False) -> dict:
        relatorio = {"criados": 0, "atualizados": 0, "inalterados": 0, "erros": [], "avisos": [],
                     "abortado": False, "dry_run": dry_run}
        linhas = self._ler(caminho_csv)
        status_loinc = self._status_loinc(linhas)

        validos, vistos = [], {}
        for n, r in linhas:
            try:
                item = self._validar(r, status_loinc, relatorio["avisos"], n)
            except ValueError as ex:
                relatorio["erros"].append({"linha": n, "nome": (r.get("nome_exame") or "").strip(), "motivo": str(ex)})
                continue
            chave = item["nome_normalizado"]
            if chave in vistos:
                relatorio["erros"].append({"linha": n, "nome": item["nome_exame"],
                                           "motivo": f"nome repetido (igual ao da linha {vistos[chave]})"})
                continue
            vistos[chave] = n
            validos.append(item)

        if relatorio["erros"] and not ignorar_erros:
            relatorio["abortado"] = True
            return relatorio
        try:
            for item in validos:
                self._aplicar(item, relatorio, sobrescrever_ativo)
            db.session.rollback() if dry_run else db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return relatorio

    # ------------------------------------------------------------------
    @staticmethod
    def _ler(caminho):
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            leitor = csv.DictReader(f, delimiter=";")
            faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in (leitor.fieldnames or [])]
            if faltando:
                raise ValueError(f"{caminho}: colunas ausentes {faltando}")
            return [(i, r) for i, r in enumerate(leitor, start=2)]  # linha 1 = cabeçalho

    @staticmethod
    def _status_loinc(linhas):
        codigos = {(r.get("codigo_loinc") or "").strip() for _, r in linhas} - {""}
        if not codigos:
            return {}
        return {t.loinc_num: t.status for t in LoincTermo.query.filter(LoincTermo.loinc_num.in_(codigos)).all()}

    @staticmethod
    def _validar(r, status_loinc, avisos, n):
        nome = _txt(r.get("nome_exame"))
        if not nome:
            raise ValueError("nome_exame vazio")
        if len(nome) > 255:
            raise ValueError("nome_exame com mais de 255 caracteres")
        nome_en = _txt(r.get("nome_exame_en"))
        if nome_en and len(nome_en) > 255:
            raise ValueError("nome_exame_en com mais de 255 caracteres")
        tipo = (r.get("tipo") or "").strip().lower()
        if tipo not in TIPOS:
            raise ValueError(f"tipo inválido '{tipo}' (use {', '.join(sorted(TIPOS))})")
        material, material_en = _txt(r.get("material")), _txt(r.get("material_en"))
        if (material and len(material) > 100) or (material_en and len(material_en) > 100):
            raise ValueError("material/material_en com mais de 100 caracteres")

        sinonimos, vistos = [], {normalizar_texto(nome)}
        for s in (r.get("sinonimos_busca") or "").split(","):
            s = _txt(s)
            if s and normalizar_texto(s) not in vistos:
                vistos.add(normalizar_texto(s))
                sinonimos.append(s)

        loinc = (r.get("codigo_loinc") or "").strip() or None
        if loinc:
            if not RE_LOINC.match(loinc):
                raise ValueError(f"codigo_loinc '{loinc}' não parece um código LOINC (ex.: 2345-7)")
            if tipo != "laboratorial":
                raise ValueError("codigo_loinc só se aplica a exames laboratoriais")
            if loinc not in status_loinc:
                raise ValueError(f"codigo_loinc {loinc} não existe em loinc_termo (rode a carga do LOINC)")
            if status_loinc[loinc] == "DEPRECATED":
                raise ValueError(f"codigo_loinc {loinc} está DEPRECATED")
            if status_loinc[loinc] != "ACTIVE":
                avisos.append({"linha": n, "nome": nome, "aviso": f"codigo_loinc {loinc} com status {status_loinc[loinc]}"})

        ativo_txt = (r.get("ativo") or "").strip().lower()
        if ativo_txt in SIM:
            ativo = True
        elif ativo_txt in NAO:
            ativo = False
        else:
            raise ValueError(f"ativo inválido '{ativo_txt}' (use s ou n)")

        return {"nome_exame": nome, "nome_normalizado": normalizar_texto(nome), "nome_exame_en": nome_en,
                "tipo": tipo, "material": material, "material_en": material_en,
                "sinonimos_busca_json": sinonimos or None, "codigo_loinc": loinc, "ativo": ativo,
                "busca_normalizada": montar_busca_normalizada(nome, nome_en, sinonimos)}

    @staticmethod
    def _aplicar(item, relatorio, sobrescrever_ativo):
        existente = CatalogoExames.query.filter_by(nome_normalizado=item["nome_normalizado"]).first()
        if not existente:  # linha antiga ainda sem nome_normalizado, mesmo nome
            existente = CatalogoExames.query.filter(
                CatalogoExames.nome_normalizado.is_(None),
                func.lower(CatalogoExames.nome_exame) == item["nome_exame"].lower()).first()
        if not existente:
            db.session.add(CatalogoExames(**item))
            relatorio["criados"] += 1
            return
        mudou = existente.nome_normalizado != item["nome_normalizado"]
        for campo in CAMPOS:
            if getattr(existente, campo) != item[campo]:
                setattr(existente, campo, item[campo])
                mudou = True
        if sobrescrever_ativo and existente.ativo != item["ativo"]:
            existente.ativo = item["ativo"]
            mudou = True
        existente.nome_normalizado = item["nome_normalizado"]
        relatorio["atualizados" if mudou else "inalterados"] += 1
        if mudou:
            db.session.add(existente)


def executar(caminho_csv="seeds/exames/exames_brasil_candidatos.csv", dry_run=False,
             sobrescrever_ativo=False, ignorar_erros=False) -> dict:
    """Ponto de entrada para quem já tem app_context aberto."""
    rel = ImportarCatalogoExamesService().importar(caminho_csv, dry_run, sobrescrever_ativo, ignorar_erros)
    logger.info("Exames: %s", {k: v for k, v in rel.items() if k not in ("erros", "avisos")})
    for e in rel["erros"]:
        logger.warning("Exames erro: %s", e)
    return rel
