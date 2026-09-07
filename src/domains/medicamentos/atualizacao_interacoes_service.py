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
   resolver cada nome para o id do catálogo antes de tudo.
2. Itens cujo princípio ativo não existe no catálogo são pulados e
   reportados (não criamos medicamento novo a partir da fonte de
   interação -- catálogo só é alimentado por
   AtualizacaoMedicamentosService/ANVISA).
3. Ordena o par pelo menor id primeiro.
4. Busca a interação exata para esse par ordenado.
5. Se não existe -> cria. Se existe e diverge -> atualiza. Sempre
   aplica direto (mesmo padrão do catálogo: automático e confiável o
   bastante para não exigir revisão humana prévia).
"""

from src.models.catalogos.interacoes_medicamentos import InteracoesMedicamentos
from .repository import CatalogoMedicamentosRepository, InteracoesMedicamentosRepository


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
        criadas = []
        atualizadas = []
        ignoradas_sem_catalogo = []
        inalteradas = 0

        for item in itens_fonte_externa:
            nome_a = item.get("principio_ativo_a")
            nome_b = item.get("principio_ativo_b")
            if not nome_a or not nome_b:
                continue

            medicamento_a = self.repo_catalogo.find_por_principio_ativo_exato(nome_a)
            medicamento_b = self.repo_catalogo.find_por_principio_ativo_exato(nome_b)

            if not medicamento_a or not medicamento_b:
                # Não criamos medicamento a partir da fonte de
                # interação -- só reportamos para investigação manual
                # (pode ser nome grafado diferente do catálogo, ou
                # princípio ativo que a ANVISA ainda não trouxe).
                ignoradas_sem_catalogo.append({"principio_ativo_a": nome_a, "principio_ativo_b": nome_b})
                continue

            # Ordena pelo menor id primeiro -- é essa regra que
            # garante, em código, o mesmo invariante que o
            # UniqueConstraint do banco espera.
            id_a, id_b = sorted([medicamento_a.id, medicamento_b.id])

            existente = self.repo_interacoes.find_por_par_ordenado(id_a, id_b)

            if not existente:
                nova = InteracoesMedicamentos(
                    id_medicamento_a=id_a,
                    id_medicamento_b=id_b,
                    gravidade=item.get("gravidade"),
                    mecanismo_efeito=item.get("mecanismo_efeito"),
                    recomendacao=item.get("recomendacao"),
                    acao=item.get("acao"),
                )
                self.repo_interacoes.save(nova)
                criadas.append(nova)
                continue

            campos_fonte = {
                "gravidade": item.get("gravidade"),
                "mecanismo_efeito": item.get("mecanismo_efeito"),
                "recomendacao": item.get("recomendacao"),
                "acao": item.get("acao"),
            }
            # Só considera os campos que a fonte de fato forneceu
            # (valor não-None) tanto para detectar divergência quanto
            # para aplicar update -- protege contra apagar dado bom
            # com um None de fonte que não cobre aquele campo.
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
                self.repo_interacoes.save(existente)
                atualizadas.append(existente)
            else:
                inalteradas += 1

        return {
            "criadas": [i.to_dict() for i in criadas],
            "atualizadas": [i.to_dict() for i in atualizadas],
            "ignoradas_sem_catalogo": ignoradas_sem_catalogo,
            "total_inalteradas": inalteradas,
        }