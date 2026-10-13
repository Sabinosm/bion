"""
Único ponto da aplicação autorizado a criar ou editar linhas de
interações medicamentosas. Mesmo espírito de
AtualizacaoMedicamentosService (catálogo): processo automático do
sistema, não ação de usuário, sem endpoint HTTP.

Fonte: Detecta Interações (CRF-MG / UFSJ) -- ver decisão registrada em
resumo_medicamentos_bion.md. Base gratuita, com lastro acadêmico, mas
licenciada como CC BY-NC-SA (não-comercial por padrão) -- confirmar
com os autores antes de depender disso em produção comercial.

Resolve aqui, em código, a regra que o UniqueConstraint do banco só
consegue impor parcialmente: o par (id_medicamento_a, id_medicamento_b)
deve SEMPRE ser gravado com o menor id em id_medicamento_a. Sem isso,
o mesmo par podia ser inserido duas vezes em ordem trocada (A=5,B=3 e
depois A=3,B=5), burlando o UniqueConstraint por serem, para o banco,
linhas "diferentes".

Fluxo:
1. Cada item da fonte externa vem como par de nomes/princípios ativos
   (ex: "dipirona" x "varfarina"), não como IDs internos -- é preciso
   resolver cada nome para o id do catálogo (pelo nome normalizado ou
   sinônimo, ver normalizacao.py) antes de tudo.
2. Itens cujo princípio ativo não existe no catálogo são pulados e
   reportados (não criamos medicamento novo a partir da fonte de
   interação -- catálogo só é alimentado por
   AtualizacaoMedicamentosService/ANVISA).
3. Ordena o par pelo menor id primeiro.
4. Busca a interação exata para esse par ordenado.
5. Se não existe -> cria. Se existe e diverge -> atualiza. Sempre
   aplica direto (mesmo padrão do catálogo: automático e confiável o
   bastante para não exigir revisão humana prévia).
6. Em todo par conferido, grava fonte_origem e ultima_verificacao_em.
7. Grava em lotes (TAMANHO_LOTE itens por commit), com rollback do lote
   em andamento se algo falhar -- mesmo comportamento do catálogo.
"""

import logging
from datetime import datetime, timezone

from src.models import db
from src.models.catalogos.interacoes_medicamentos import InteracoesMedicamentos
from ..repository import CatalogoMedicamentosRepository, InteracoesMedicamentosRepository

logger = logging.getLogger(__name__)

TAMANHO_LOTE = 500


class AtualizacaoInteracoesService:

    def __init__(self):
        self.repo_catalogo = CatalogoMedicamentosRepository()
        self.repo_interacoes = InteracoesMedicamentosRepository()

    def sincronizar(self, itens_fonte_externa: list[dict], fonte: str):
        """
        itens_fonte_externa: lista de dicts vindos da fonte externa,
        cada um com pelo menos:
        {
            "principio_ativo_a": str,
            "principio_ativo_b": str,
            "gravidade": str | None,
            "mecanismo_efeito": str | None,
            "recomendacao": str | None,
            "acao": str | None,
        }
        Campos com valor None no item da fonte são tratados como "esta
        fonte não fornece essa informação" e NÃO sobrescrevem valor já
        existente no banco -- importante porque a fonte atual
        (Detecta Interações) não expõe gravidade, e sem essa proteção
        cada sincronização apagaria uma gravidade que tivesse sido
        preenchida por outra fonte ou curadoria manual.
        fonte: identificador da fonte (ex: "detecta-interacoes-crfmg").
        """
        agora = datetime.now(timezone.utc)
        criadas = []
        atualizadas = []
        ignoradas_sem_catalogo = []
        inalteradas = 0
        pendentes = 0

        try:
            for item in itens_fonte_externa:
                resultado, objeto = self._processar_item(item, fonte, agora)

                if resultado == "criada":
                    criadas.append(objeto)
                elif resultado == "atualizada":
                    atualizadas.append(objeto)
                elif resultado == "inalterada":
                    inalteradas += 1
                elif resultado == "ignorada_sem_catalogo":
                    ignoradas_sem_catalogo.append(objeto)

                if resultado in ("criada", "atualizada", "inalterada"):
                    pendentes += 1
                    if pendentes >= TAMANHO_LOTE:
                        db.session.commit()
                        pendentes = 0
                        logger.info(
                            "Interações: %d criadas, %d atualizadas, %d inalteradas até agora",
                            len(criadas), len(atualizadas), inalteradas,
                        )

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return {
            "criadas": [i.to_dict() for i in criadas],
            "atualizadas": [i.to_dict() for i in atualizadas],
            "ignoradas_sem_catalogo": ignoradas_sem_catalogo,
            "total_inalteradas": inalteradas,
        }

    def _processar_item(self, item: dict, fonte: str, agora):
        """Retorna (resultado, objeto) com resultado em: 'invalida',
        'ignorada_sem_catalogo', 'criada', 'atualizada', 'inalterada'."""
        nome_a = item.get("principio_ativo_a")
        nome_b = item.get("principio_ativo_b")
        if not nome_a or not nome_b:
            return "invalida", None

        medicamento_a = self.repo_catalogo.find_por_nome_normalizado(nome_a)
        medicamento_b = self.repo_catalogo.find_por_nome_normalizado(nome_b)

        if not medicamento_a or not medicamento_b:
            # Não criamos medicamento a partir da fonte de interação --
            # só reportamos para investigação manual (pode ser nome
            # grafado diferente do catálogo: nesse caso, cadastrar um
            # sinônimo; ou princípio ativo que a ANVISA ainda não trouxe).
            return "ignorada_sem_catalogo", {
                "principio_ativo_a": nome_a,
                "principio_ativo_b": nome_b,
            }

        # Ordena pelo menor id primeiro -- é essa regra que garante, em
        # código, o mesmo invariante que o UniqueConstraint do banco espera.
        id_a, id_b = sorted([medicamento_a.id, medicamento_b.id])
        if id_a == id_b:
            # Nomes diferentes que resolveram para o mesmo medicamento
            # (ex: sal e base): não é uma interação entre dois fármacos.
            return "invalida", None

        existente = self.repo_interacoes.find_por_par_ordenado(id_a, id_b)

        if not existente:
            nova = InteracoesMedicamentos(
                id_medicamento_a=id_a,
                id_medicamento_b=id_b,
                gravidade=item.get("gravidade"),
                mecanismo_efeito=item.get("mecanismo_efeito"),
                recomendacao=item.get("recomendacao"),
                acao=item.get("acao"),
                fonte_origem=fonte,
                ultima_verificacao_em=agora,
            )
            self.repo_interacoes.add(nova)
            return "criada", nova

        campos_fonte = {
            "gravidade": item.get("gravidade"),
            "mecanismo_efeito": item.get("mecanismo_efeito"),
            "recomendacao": item.get("recomendacao"),
            "acao": item.get("acao"),
        }
        # Só considera os campos que a fonte de fato forneceu (valor
        # não-None) tanto para detectar divergência quanto para aplicar
        # update -- protege contra apagar dado bom com um None de fonte
        # que não cobre aquele campo.
        campos_para_atualizar = {
            campo: valor for campo, valor in campos_fonte.items() if valor is not None
        }

        divergiu = any(
            getattr(existente, campo) != valor
            for campo, valor in campos_para_atualizar.items()
        )

        if divergiu:
            for campo, valor in campos_para_atualizar.items():
                setattr(existente, campo, valor)
        existente.fonte_origem = fonte
        existente.ultima_verificacao_em = agora
        self.repo_interacoes.add(existente)

        return ("atualizada" if divergiu else "inalterada"), existente