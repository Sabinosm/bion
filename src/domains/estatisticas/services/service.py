from .estatisticas_usuario import EstatisticasUsuario
from .estatisticas_paciente import EstatisticasPaciente
from .estatisticas_consulta import EstatisticasConsulta
from .estatisticas_atendimento import EstatisticasAtendimento
from .estatisticas_alergia import EstatisticasAlergia
from .estatisticas_prescricao_exame import EstatisticasPrescricaoExame
from .estatisticas_resultado_prescricao import EstatisticasResultadoPrescricao

eu = EstatisticasUsuario()
ep = EstatisticasPaciente()
ec = EstatisticasConsulta()
ea = EstatisticasAtendimento()
eal = EstatisticasAlergia()
epe = EstatisticasPrescricaoExame()
erp = EstatisticasResultadoPrescricao()


class EstatisticasService:

    def estatisticas_geral(self, id_empresa):
        estatisticas = {
            "total_profissionais": eu.contagem_profissionais(id_empresa=id_empresa),
            "profissionais_pendentes": eu.profissonais_status(id_empresa=id_empresa, status="pendente"),
            "profissionais_ativos": eu.profissonais_status(id_empresa=id_empresa, status="ativo"),
            "consultas_hoje": ec.consultas_hoje(id_empresa=id_empresa),
            "pacientes_cadastrados": ep.pacientes_cadastrados(id_empresa=id_empresa),
        }
        return estatisticas

    # --- A1: Volume de atendimentos ---
    def volume_atendimentos(self, id_empresa, dias=30):
        return ec.volume_por_dia(id_empresa=id_empresa, dias=dias)

    # --- A2: Tempo médio de atendimento ---
    def tempo_medio_atendimento(self, id_empresa, dias=30):
        return ea.tempo_medio_por_tipo(id_empresa=id_empresa, dias=dias)

    # --- A3: Taxa de conclusão vs. abandono ---
    def taxa_conclusao(self, id_empresa, dias=30):
        return ec.taxa_conclusao(id_empresa=id_empresa, dias=dias)

    # --- A4: Efetivo ativo por papel ---
    def efetivo_ativo(self, id_empresa):
        return eu.efetivo_ativo(id_empresa=id_empresa)

    # --- A5: Engajamento/atividade da equipe ---
    def engajamento_equipe(self, id_empresa, dias=7):
        return eu.engajamento_equipe(id_empresa=id_empresa, dias=dias)

    # --- D2: Alergias mais reportadas ---
    def alergias_top_substancias(self, id_empresa, limite=10):
        return eal.top_substancias(id_empresa=id_empresa, limite=limite)

    def alergia_gravidade_por_substancia(self, id_empresa, substancia):
        return eal.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)

    # --- D3: Urgência de exames -- IA vs. profissional ---
    def urgencia_exames_por_origem(self, id_empresa, dias=30):
        return epe.urgencia_por_origem(id_empresa=id_empresa, dias=dias)

    # --- C1: Doenças mais comuns por região ---
    def top_cid_por_regiao(self, id_empresa, dias=14, limite=10):
        return erp.top_cid_por_regiao(id_empresa=id_empresa, dias=dias, limite=limite)

    # --- C3: Incidência por 100 mil habitantes ---
    def incidencia_por_regiao(self, id_empresa, dias=14):
        return erp.incidencia_por_regiao(id_empresa=id_empresa, dias=dias)