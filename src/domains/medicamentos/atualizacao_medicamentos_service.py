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
   ver comando_sincronizar_catalogo.py) -- não há endpoint HTTP nem
   checagem de papel aqui, pois não é ação de usuário.
2. Base é compartilhada entre empresas -- não há id_empresa em
   catalogo_medicamentos nem neste service.
3. Para cada item vindo da fonte externa, busca correspondente exato
   por principio_ativo no catálogo atual.
4. Se não existe -> cria.
5. Se existe e os dados divergem -> aplica a atualização diretamente
   (decisão revisada: o processo agora é automático e confiável o
   bastante para aplicar sozinho) e grava um LogSincronizacaoCatalogo
   com o estado antes/depois.
6. Atualiza ultima_verificacao_em em todos os itens conferidos, tenham
   ou não mudado -- é isso que sustenta "quando foi checado pela
   última vez".
"""

from datetime import datetime, timezone

from src.models import db
from src.models.catalogos.catalogo_medicamentos import CatalogoMedicamentos
from src.models.catalogos.log_sincronizacao_catalogo import LogSincronizacaoCatalogo
from .repository import CatalogoMedicamentosRepository


class AtualizacaoMedicamentosService:

    def __init__(self):
        self.repo = CatalogoMedicamentosRepository()

    def sincronizar(self, itens_fonte_externa: list[dict], fonte: str):
        """
        itens_fonte_externa: lista de dicts vindos da fonte confiável,
        cada um com pelo menos principio_ativo, classe_farmaceutica,
        nomes_comerciais.
        fonte: identificador da fonte (ex: "ANVISA-DCB-2026-01").
        """
        agora = datetime.now(timezone.utc)
        criados = []
        atualizados = []
        inalterados = 0

        for item in itens_fonte_externa:
            principio_ativo = item.get("principio_ativo")
            if not principio_ativo:
                continue

            existente = self.repo.find_por_principio_ativo_exato(principio_ativo)

            if not existente:
                novo = CatalogoMedicamentos(
                    principio_ativo=principio_ativo,
                    classe_farmaceutica=item.get("classe_farmaceutica"),
                    nomes_comerciais_json=item.get("nomes_comerciais"),
                    fonte_origem=fonte,
                    ultima_verificacao_em=agora,
                )
                self.repo.save(novo)
                self._registrar_log(novo, "criado", fonte, dados_antes=None)
                criados.append(novo)
                continue

            divergiu = (
                existente.classe_farmaceutica != item.get("classe_farmaceutica")
                or existente.nomes_comerciais_json != item.get("nomes_comerciais")
            )

            if divergiu:
                dados_antes = {
                    "classe_farmaceutica": existente.classe_farmaceutica,
                    "nomes_comerciais": existente.nomes_comerciais_json,
                }
                existente.classe_farmaceutica = item.get("classe_farmaceutica")
                existente.nomes_comerciais_json = item.get("nomes_comerciais")
                existente.fonte_origem = fonte
                existente.ultima_verificacao_em = agora
                self.repo.save(existente)
                self._registrar_log(existente, "atualizado", fonte, dados_antes=dados_antes)
                atualizados.append(existente)
            else:
                existente.fonte_origem = fonte
                existente.ultima_verificacao_em = agora
                self.repo.save(existente)
                inalterados += 1

        return {
            "criados": [m.to_dict() for m in criados],
            "atualizados": [m.to_dict() for m in atualizados],
            "total_inalterados": inalterados,
        }

    def _registrar_log(self, medicamento: CatalogoMedicamentos, tipo_alteracao: str,
                        fonte: str, dados_antes: dict | None):
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
        db.session.commit()