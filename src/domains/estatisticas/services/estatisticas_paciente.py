"""
estatisticas_paciente.py

Estatísticas da base de pacientes: cadastros, doenças crônicas mais comuns,
percentual em uso contínuo de medicação e distribuição de tipo sanguíneo. São
fotos do cadastro acumulado, sem filtro de período, e por isso sem nível nem
comparação com período anterior.
"""

from src.domains.paciente.services.paciente_service import PacienteService
from src.domains.paciente.services.doenca_cronica_service import DoencaCronicaService
from src.domains.paciente.services.medicamento_em_uso_service import MedicamentoEmUsoService
from src.domains.paciente.services.obs_tipo_sanguineo_service import ObservacaoTipoSanguineoService
from src.domains.estatisticas.interpretacao_helper import interpretacao_sem_nivel

_paciente_svc = PacienteService()
_doenca_cronica_svc = DoencaCronicaService()
_medicamento_em_uso_svc = MedicamentoEmUsoService()
_tipo_sanguineo_svc = ObservacaoTipoSanguineoService()


class EstatisticasPaciente:

    def pacientes_cadastrados_hoje(self, id_empresa):
        return _paciente_svc.count_pacientes_hoje(id_empresa=id_empresa)

    def pacientes_cadastrados(self, id_empresa):
        return _paciente_svc.count_pacientes(id_empresa=id_empresa)

    def doencas_cronicas_top(self, id_empresa, limite=10):
        """Ranking das doenças crônicas mais comuns na base (F1).

        Ranking acumulado da base (sem filtro de dias); sem nível ou
        comparação, pois não há "período anterior" — é o estado atual
        do cadastro, não um evento datado.

        Retorna: {"ranking": [...], "leitura": str, "interpretacao": {...}}
        """
        ranking = _doenca_cronica_svc.top_cid_ativas(id_empresa=id_empresa, limite=limite)

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

    def uso_continuo_medicacao(self, id_empresa):
        """Percentual de pacientes em uso contínuo de medicação (F2).

        Retorna: {"total_pacientes", "em_uso_continuo", "percentual", "leitura"}
        """
        dados = _medicamento_em_uso_svc.percentual_pacientes_em_uso_continuo(id_empresa=id_empresa)
        leitura = f"{dados['percentual']}% dos pacientes cadastrados estão em uso contínuo de medicação"
        return {**dados, "leitura": leitura}

    def distribuicao_tipo_sanguineo(self, id_empresa):
        """Distribuição de tipo sanguíneo na base de pacientes (F3).

        Retorna: {"distribuicao": {...}, "leitura": str}
        """
        distribuicao = _tipo_sanguineo_svc.distribuicao_tipo_sanguineo(id_empresa=id_empresa)
        total = sum(distribuicao.values())

        leitura = None
        if total:
            tipo_top, qtd_top = max(distribuicao.items(), key=lambda item: item[1])
            pct = round((qtd_top / total) * 100, 1)
            leitura = f"{tipo_top} é o tipo sanguíneo mais comum na base ({pct}% dos pacientes com tipo registrado)"

        return {"distribuicao": distribuicao, "leitura": leitura}