"""
Único ponto da aplicação autorizado a criar ou editar linhas do
catálogo de medicamentos. Todo o resto do sistema (médico, IA,
CatalogoMedicamentosService) trata o catálogo como somente-leitura.

Este service usa o mesmo CatalogoMedicamentosRepository -- não duplica
acesso a banco --, mas fica isolado em arquivo/classe própria porque a
lógica de sincronização e o registro de auditoria são responsabilidade
diferente do fluxo comum de leitura.

Fluxo:
1. Disparado pelo processo automático do sistema (CLI/job agendado,
   ver sincronizar_catalogo_service.py e cli_sincronizacao.py) -- não
   há endpoint HTTP nem checagem de papel aqui, pois não é ação de
   usuário.
2. Base é compartilhada entre empresas -- não há id_empresa em
   catalogo_medicamentos nem neste service.
3. Para cada item vindo da fonte externa, busca o correspondente pelo
   nome normalizado (sem acento, minúsculo, sem prefixo de sal) ou por
   sinônimo cadastrado -- ver normalizacao.py.
4. Se não existe -> cria.
5. Se existe e os dados divergem -> aplica a atualização diretamente
   (decisão revisada: o processo agora é automático e confiável o
   bastante para aplicar sozinho) e grava um LogSincronizacaoCatalogo
   com o estado antes/depois.
6. Atualiza ultima_verificacao_em em todos os itens conferidos, tenham
   ou não mudado -- é isso que sustenta "quando foi checado pela
   última vez".
7. Grava em lotes (TAMANHO_LOTE itens por commit). O log entra na mesma
   transação do item. Se algo falha, o lote em andamento sofre rollback
   e a exceção sobe; lotes já confirmados permanecem, e como a rotina é
   idempotente, rodar de novo continua de onde parou.
"""

import logging
from datetime import datetime, timezone

from src.models import db
from src.models.catalogos.catalogo_medicamentos import CatalogoMedicamentos
from src.models.catalogos.log_sincronizacao_catalogo import LogSincronizacaoCatalogo
from ..repository import CatalogoMedicamentosRepository
from ..normalizacao import normalizar_nome

logger = logging.getLogger(__name__)

TAMANHO_LOTE = 500


class AtualizacaoMedicamentosService:

    def __init__(self):
        self.repo = CatalogoMedicamentosRepository()

    def sincronizar(self, itens_fonte_externa: list[dict], fonte: str):
        """
        itens_fonte_externa: lista de dicts vindos da fonte confiável,
        cada um com pelo menos principio_ativo, classe_farmaceutica,
        nomes_comerciais.
        fonte: identificador da fonte (ex: "ANVISA-DADOS-ABERTOS-2026-10-13").
        """
        agora = datetime.now(timezone.utc)
        criados = []
        atualizados = []
        inalterados = 0
        pendentes = 0

        try:
            for item in itens_fonte_externa:
                principio_ativo = item.get("principio_ativo")
                if not principio_ativo:
                    continue

                existente = self.repo.find_por_nome_normalizado(principio_ativo)

                if not existente:
                    novo = CatalogoMedicamentos(
                        principio_ativo=principio_ativo,
                        principio_ativo_normalizado=normalizar_nome(principio_ativo),
                        classe_farmaceutica=item.get("classe_farmaceutica"),
                        nomes_comerciais_json=item.get("nomes_comerciais"),
                        fonte_origem=fonte,
                        ultima_verificacao_em=agora,
                    )
                    self.repo.add(novo)  # flush: garante novo.id para o log
                    self._registrar_log(novo, "criado", fonte, dados_antes=None)
                    criados.append(novo)
                else:
                    divergiu = (
                        existente.classe_farmaceutica != item.get("classe_farmaceutica")
                        or existente.nomes_comerciais_json != item.get("nomes_comerciais")
                    )
                    dados_antes = {
                        "classe_farmaceutica": existente.classe_farmaceutica,
                        "nomes_comerciais": existente.nomes_comerciais_json,
                    }
                    if divergiu:
                        existente.classe_farmaceutica = item.get("classe_farmaceutica")
                        existente.nomes_comerciais_json = item.get("nomes_comerciais")
                    existente.fonte_origem = fonte
                    existente.ultima_verificacao_em = agora
                    self.repo.add(existente)

                    if divergiu:
                        self._registrar_log(existente, "atualizado", fonte, dados_antes)
                        atualizados.append(existente)
                    else:
                        inalterados += 1

                pendentes += 1
                if pendentes >= TAMANHO_LOTE:
                    db.session.commit()
                    pendentes = 0
                    logger.info(
                        "Catálogo: %d criados, %d atualizados, %d inalterados até agora",
                        len(criados), len(atualizados), inalterados,
                    )

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return {
            "criados": [m.to_dict() for m in criados],
            "atualizados": [m.to_dict() for m in atualizados],
            "total_inalterados": inalterados,
        }

    def _registrar_log(self, medicamento: CatalogoMedicamentos, tipo_alteracao: str,
                        fonte: str, dados_antes: dict | None):
        # Sem commit: o log entra na mesma transação do lote.
        log = LogSincronizacaoCatalogo(
            id_catalogo=medicamento.id,
            tipo_alteracao=tipo_alteracao,
            fonte=fonte,
            dados_antes_json=dados_antes,
            dados_depois_json={
                "classe_farmaceutica": medicamento.classe_farmaceutica,
                "nomes_comerciais": medicamento.nomes_comerciais_json,
            },
        )
        db.session.add(log)