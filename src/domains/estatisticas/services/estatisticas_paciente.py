from src.domains.estatisticas.interpretacao_helper import interpretacao_sem_nivel
from src.domains.paciente.services import PacienteService

ps = PacienteService()


class EstatisticasPaciente:
    def pacientes_cadastrados_hoje(self, id_empresa):
        return ps.count_pacientes_hoje(id_empresa=id_empresa)
 
    def pacientes_cadastrados(self, id_empresa):
        return ps.count_pacientes(id_empresa=id_empresa)
 
    # --- F1: Doenças crônicas mais comuns na base ---
    def doencas_cronicas_top(self, id_empresa, limite=10):
        """Grupo 2 -- ranking acumulado da base (sem filtro de dias),
        sem nivel/comparacao: não há "período anterior" aqui, é o
        estado atual do cadastro, não um evento datado.
 
        Retorna: {"ranking": [...], "leitura": str, "interpretacao": {...}}
        """
        ranking = ps.top_cid_ativas(id_empresa=id_empresa, limite=limite)
 
        leitura = None
        if ranking:
            principal = ranking[0]
            leitura = (
                f"{principal['descricao_cid10']} ({principal['codigo_cid10']}) é a condição crônica "
                f"mais comum na base, presente em {principal['total']} pacientes"
            )
 
        interpretacao = interpretacao_sem_nivel(
            texto="Perfil de morbidade da base -- alto volume numa condição sinaliza necessidade de programas de cuidado continuado, não é 'bom' ou 'ruim' por si só",
            direcao="neutro",
            comparacao=None,
        )
 
        return {"ranking": ranking, "leitura": leitura, "interpretacao": interpretacao}
 
    # --- F2: Pacientes em uso contínuo de medicação ---
    def uso_continuo_medicacao(self, id_empresa):
        """Retorna: {"total_pacientes", "em_uso_continuo", "percentual", "leitura"}"""
        dados = ps.percentual_em_uso_continuo(id_empresa=id_empresa)
        leitura = f"{dados['percentual']}% dos pacientes cadastrados estão em uso contínuo de medicação"
        return {**dados, "leitura": leitura}
 
    # --- F3: Distribuição de tipo sanguíneo na base ---
    def distribuicao_tipo_sanguineo(self, id_empresa):
        """Retorna: {"distribuicao": {...}, "leitura": str}"""
        distribuicao = ps.distribuicao_tipo_sanguineo(id_empresa=id_empresa)
        total = sum(distribuicao.values())
 
        leitura = None
        if total:
            tipo_top, qtd_top = max(distribuicao.items(), key=lambda item: item[1])
            pct = round((qtd_top / total) * 100, 1)
            leitura = f"{tipo_top} é o tipo sanguíneo mais comum na base ({pct}% dos pacientes com tipo registrado)"
 
        return {"distribuicao": distribuicao, "leitura": leitura}
 
            