from .estatisticas_usuario import EstatisticasUsuario
from .estatisticas_paciente import EstatisticasPaciente
from .estatisticas_consulta import EstatisticasConsulta
from .estatisticas_atendimento import EstatisticasAtendimento
from .estatisticas_alergia import EstatisticasAlergia
from .estatisticas_prescricao_exame import EstatisticasPrescricaoExame
from .estatisticas_resultado_prescricao import EstatisticasResultadoPrescricao
from .estatisticas_outputbion import EstatisticasOutputBion
from .estatisticas_input_protocolo import EstatisticasInputProtocolo
from .estatisticas_interacoes_medicamentos import EstatisticasInteracoesMedicamentos
from .estatisticas_prescricao import EstatisticasPrescricao

eu = EstatisticasUsuario()
ep = EstatisticasPaciente()
ec = EstatisticasConsulta()
ea = EstatisticasAtendimento()
eal = EstatisticasAlergia()
epe = EstatisticasPrescricaoExame()
erp = EstatisticasResultadoPrescricao()
eob = EstatisticasOutputBion()
eip = EstatisticasInputProtocolo()
eim = EstatisticasInteracoesMedicamentos()
epr = EstatisticasPrescricao()


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
 
    # --- A1-A5: operacional ---
    def volume_atendimentos(self, id_empresa, dias=30):
        return ec.volume_por_dia(id_empresa=id_empresa, dias=dias)
 
    def tempo_medio_atendimento(self, id_empresa, dias=30):
        return ea.tempo_medio_por_tipo(id_empresa=id_empresa, dias=dias)
 
    def taxa_conclusao(self, id_empresa, dias=30):
        return ec.taxa_conclusao(id_empresa=id_empresa, dias=dias)
 
    def efetivo_ativo(self, id_empresa):
        return eu.efetivo_ativo(id_empresa=id_empresa)
 
    def engajamento_equipe(self, id_empresa, dias=7):
        return eu.engajamento_equipe(id_empresa=id_empresa, dias=dias)
 
    # --- B1, B2, B4, E3: qualidade da IA ---
    def confianca_media_ia(self, id_empresa, dias=30):
        return eob.confianca_media(id_empresa=id_empresa, dias=dias)
 
    def completude_media_ia(self, id_empresa, dias=30):
        return eob.completude_media(id_empresa=id_empresa, dias=dias)
 
    def versoes_ia_em_uso(self, id_empresa, dias=30):
        return eob.versoes_em_uso(id_empresa=id_empresa, dias=dias)
 
    def correlacao_completude_confianca(self, id_empresa, dias=30):
        return eob.correlacao_completude_confianca(id_empresa=id_empresa, dias=dias)
 
    # --- C1-C5: epidemiológico ---
    def top_cid_por_regiao(self, id_empresa, dias=14, limite=10):
        return erp.top_cid_por_regiao(id_empresa=id_empresa, dias=dias, limite=limite)
 
    def evolucao_cid(self, id_empresa, codigo_cid10, dias=30):
        return erp.evolucao_cid(id_empresa=id_empresa, codigo_cid10=codigo_cid10, dias=dias)
 
    def incidencia_por_regiao(self, id_empresa, dias=14):
        return erp.incidencia_por_regiao(id_empresa=id_empresa, dias=dias)
 
    def tempo_ate_atendimento(self, id_empresa, dias=30):
        return ea.tempo_ate_atendimento(id_empresa=id_empresa, dias=dias)
 
    def queixas_mais_frequentes(self, id_empresa, dias=30, top=15):
        return eip.queixas_mais_frequentes(id_empresa=id_empresa, dias=dias, top=top)
 
    # --- D1-D4: farmacovigilância ---
    def interacoes_por_gravidade(self):
        return eim.por_gravidade()
 
    def alergias_top_substancias(self, id_empresa, limite=10):
        return eal.top_substancias(id_empresa=id_empresa, limite=limite)
 
    def alergia_gravidade_por_substancia(self, id_empresa, substancia):
        return eal.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)
 
    def urgencia_exames_por_origem(self, id_empresa, dias=30):
        return epe.urgencia_por_origem(id_empresa=id_empresa, dias=dias)
 
    def medicamentos_top_por_classe(self, id_empresa, dias=30, limite=10):
        return epr.top_por_classe(id_empresa=id_empresa, dias=dias, limite=limite)
 
    def medicamentos_top_principios_por_classe(self, id_empresa, classe, dias=30, limite=10):
        return epr.top_principios_ativos_por_classe(id_empresa=id_empresa, classe=classe, dias=dias, limite=limite)
 
    # --- E2: pitch executivo ---
    def tendencia_eficiencia(self, id_empresa, dias=30):
        return ea.tendencia_eficiencia(id_empresa=id_empresa, dias=dias)
 
    # --- F1-F4: histórico clínico do paciente ---
    def doencas_cronicas_top(self, id_empresa, limite=10):
        return ep.doencas_cronicas_top(id_empresa=id_empresa, limite=limite)
 
    def uso_continuo_medicacao(self, id_empresa):
        return ep.uso_continuo_medicacao(id_empresa=id_empresa)
 
    def distribuicao_tipo_sanguineo(self, id_empresa):
        return ep.distribuicao_tipo_sanguineo(id_empresa=id_empresa)
 
    def alergias_gravidade_geral(self, id_empresa):
        return eal.gravidade_geral(id_empresa=id_empresa)