"""
Sincroniza o conteúdo de apoio dos exames com o MedlinePlus Connect (NLM).

Processo do sistema, sem endpoint HTTP; deve ser chamado por quem já tem app_context aberto.
Só consulta exames do catálogo que já têm codigo_loinc. Respeita o limite do serviço
(100 requisições/min por IP): pausa entre chamadas e, por padrão, não reconsulta o que foi
verificado nos últimos 30 dias. Em caso de erro, o conteúdo já guardado é MANTIDO.

Uso:
    from src.domains.exames.conteudo.sincronizar_conteudo_exames_service import executar
    executar(idiomas=("en",))
"""

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from src.models import db
from src.models.catalogos.catalogo_exames import CatalogoExames
from src.models.catalogos.catalogo_exames_conteudo import (
    CatalogoExamesConteudo, CatalogoExamesConteudoConsulta,
)
from .medlineplus_parser import interpretar_resposta

logger = logging.getLogger(__name__)

FONTE = "medlineplus"
BASE_URL = "https://connect.medlineplus.gov/service"
OID_LOINC = "2.16.840.1.113883.6.1"


class MedlinePlusErro(Exception):
    def __init__(self, mensagem, http_status=None):
        super().__init__(mensagem)
        self.http_status = http_status


class MedlinePlusConnectClient:
    def buscar(self, codigo_loinc: str, idioma: str = "en") -> dict:
        resp = requests.get(
            BASE_URL,
            params={
                "mainSearchCriteria.v.cs": OID_LOINC,
                "mainSearchCriteria.v.c": codigo_loinc,
                "knowledgeResponseType": "application/json",
                "informationRecipient.languageCode.c": idioma,
            },
            headers={"User-Agent": "bion-catalogo-exames"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise MedlinePlusErro(f"HTTP {resp.status_code}", resp.status_code)
        try:
            return resp.json()
        except ValueError as ex:
            raise MedlinePlusErro(f"resposta não é JSON: {ex}", resp.status_code)


def _utc(dt):
    """SQLite devolve datetime sem fuso; trata como UTC."""
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class SincronizarConteudoExamesService:

    def __init__(self, cliente=None, pausa_segundos: float = 0.7):
        self.cliente = cliente or MedlinePlusConnectClient()
        self.pausa = pausa_segundos  # 0,7 s => no máximo ~85 requisições/min

    def sincronizar(self, idiomas=("en",), max_idade_dias: int = 30, limite: int | None = None) -> dict:
        """max_idade_dias <= 0 força reconsultar tudo. limite = máximo de consultas nesta rodada."""
        resumo = {"consultados": 0, "com_conteudo": 0, "sem_conteudo": 0,
                  "pulados_recentes": 0, "erros": []}
        exames = (CatalogoExames.query.filter(CatalogoExames.codigo_loinc.isnot(None))
                  .order_by(CatalogoExames.id).all())
        for exame in exames:
            for idioma in idiomas:
                if limite is not None and resumo["consultados"] >= limite:
                    return resumo
                if self._verificado_recentemente(exame.id, idioma, max_idade_dias):
                    resumo["pulados_recentes"] += 1
                    continue
                self._sincronizar_um(exame, idioma, resumo)
                time.sleep(self.pausa)
        return resumo

    # ------------------------------------------------------------------
    def _verificado_recentemente(self, id_exame, idioma, max_idade_dias) -> bool:
        if max_idade_dias <= 0:
            return False
        c = CatalogoExamesConteudoConsulta.query.filter_by(
            id_catalogo_exame=id_exame, idioma=idioma, fonte=FONTE).first()
        if not c or c.status == "erro":
            return False
        return _utc(c.consultado_em) >= datetime.now(timezone.utc) - timedelta(days=max_idade_dias)

    def _sincronizar_um(self, exame, idioma, resumo):
        resumo["consultados"] += 1
        agora = datetime.now(timezone.utc)
        try:
            entradas = interpretar_resposta(self.cliente.buscar(exame.codigo_loinc, idioma))
        except Exception as ex:  # rede, HTTP != 200, JSON inválido: conteúdo antigo fica
            db.session.rollback()
            self._registrar_consulta(exame, idioma, "erro", agora, str(ex)[:255],
                                     getattr(ex, "http_status", None))
            db.session.commit()
            resumo["erros"].append({"exame": exame.nome_exame, "codigo_loinc": exame.codigo_loinc,
                                    "erro": str(ex)[:255]})
            logger.warning("MedlinePlus: erro em %s (%s): %s", exame.nome_exame, exame.codigo_loinc, ex)
            return
        try:
            self._gravar(exame, idioma, entradas, agora)
            status = "ok" if entradas else "sem_conteudo"
            self._registrar_consulta(exame, idioma, status, agora)
            db.session.commit()
            resumo["com_conteudo" if entradas else "sem_conteudo"] += 1
        except Exception as ex:
            db.session.rollback()
            resumo["erros"].append({"exame": exame.nome_exame, "codigo_loinc": exame.codigo_loinc,
                                    "erro": f"banco: {str(ex)[:200]}"})
            logger.exception("MedlinePlus: falha ao gravar %s", exame.nome_exame)

    def _gravar(self, exame, idioma, entradas, agora):
        existentes = {c.url_hash: c for c in CatalogoExamesConteudo.query.filter_by(
            id_catalogo_exame=exame.id, idioma=idioma, fonte=FONTE).all()}
        novos = set()
        for e in entradas:
            novos.add(e["url_hash"])
            c = existentes.get(e["url_hash"]) or CatalogoExamesConteudo(
                id_catalogo_exame=exame.id, idioma=idioma, fonte=FONTE, url_hash=e["url_hash"])
            c.tipo, c.titulo, c.url = e["tipo"], e["titulo"][:255], e["url"][:500]
            c.outros_nomes_json, c.secoes_json = e["outros_nomes"], e["secoes"]
            c.texto_plano, c.atribuicao = e["texto_plano"], (e["atribuicao"] or None)
            c.codigo_loinc_consultado, c.hash_conteudo, c.buscado_em = exame.codigo_loinc, e["hash_conteudo"], agora
            db.session.add(c)
        for h, c in existentes.items():  # resposta bem-sucedida que não traz mais a página: remove
            if h not in novos:
                db.session.delete(c)

    def _registrar_consulta(self, exame, idioma, status, agora, mensagem=None, http_status=None):
        c = CatalogoExamesConteudoConsulta.query.filter_by(
            id_catalogo_exame=exame.id, idioma=idioma, fonte=FONTE).first() or CatalogoExamesConteudoConsulta(
            id_catalogo_exame=exame.id, idioma=idioma, fonte=FONTE)
        c.codigo_loinc, c.status, c.mensagem, c.http_status, c.consultado_em = (
            exame.codigo_loinc, status, mensagem, http_status, agora)
        db.session.add(c)


def executar(idiomas=("en",), max_idade_dias: int = 30, limite: int | None = None) -> dict:
    """Ponto de entrada para quem já tem app_context aberto."""
    resumo = SincronizarConteudoExamesService().sincronizar(idiomas, max_idade_dias, limite)
    logger.info("MedlinePlus: %s", {k: v for k, v in resumo.items() if k != "erros"})
    for e in resumo["erros"]:
        logger.warning("MedlinePlus erro: %s", e)
    return resumo
