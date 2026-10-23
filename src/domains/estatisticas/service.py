"""
service.py

Fachada das estatísticas do Bion. Reúne os serviços de cada área do domínio
(usuários, pacientes, consultas, atendimentos, alergias, prescrições, saídas
da IA e protocolos) e expõe um método por métrica do dashboard, organizado
pelos grupos do catálogo: operacional, qualidade da IA, epidemiológico,
farmacovigilância, pitch executivo e histórico clínico do paciente. Cada
método é um repasse fino ao serviço da área; o cálculo e a interpretação dos
resultados vivem nesses módulos, não aqui. Os parâmetros de período e limite
chegam já definidos pela camada HTTP.
"""

from .services import (
    EstatisticasUsuario,
    EstatisticasPaciente,
    EstatisticasConsulta,
    EstatisticasAtendimento,
    EstatisticasAlergia,
    EstatisticasPrescricaoExame,
    EstatisticasResultadoPrescricao,
    EstatisticasOutputBion,
    EstatisticasInputProtocolo,
    EstatisticasInteracoesMedicamentos,
    EstatisticasPrescricao,
)


class EstatisticasService:

    def __init__(self):
        self._usuario = EstatisticasUsuario()
        self._paciente = EstatisticasPaciente()
        self._consulta = EstatisticasConsulta()
        self._atendimento = EstatisticasAtendimento()
        self._alergia = EstatisticasAlergia()
        self._exame = EstatisticasPrescricaoExame()
        self._resultado_prescricao = EstatisticasResultadoPrescricao()
        self._output_bion = EstatisticasOutputBion()
        self._input_protocolo = EstatisticasInputProtocolo()
        self._interacoes = EstatisticasInteracoesMedicamentos()
        self._prescricao = EstatisticasPrescricao()

    def estatisticas_geral(self, id_empresa: int) -> dict:
        return {
            "total_profissionais": self._usuario.contagem_profissionais(id_empresa=id_empresa),
            "profissionais_pendentes": self._usuario.profissionais_status(id_empresa=id_empresa, status="pendente"),
            "profissionais_ativos": self._usuario.profissionais_status(id_empresa=id_empresa, status="ativo"),
            "consultas_hoje": self._consulta.consultas_hoje(id_empresa=id_empresa),
            "pacientes_cadastrados": self._paciente.pacientes_cadastrados(id_empresa=id_empresa),
        }

    # --- A1-A5: operacional ---
    def volume_atendimentos(self, id_empresa: int, dias: int = 30):
        return self._consulta.volume_por_dia(id_empresa=id_empresa, dias=dias)

    def tempo_medio_atendimento(self, id_empresa: int, dias: int = 30):
        return self._atendimento.tempo_medio_por_tipo(id_empresa=id_empresa, dias=dias)

    def taxa_conclusao(self, id_empresa: int, dias: int = 30):
        return self._consulta.taxa_conclusao(id_empresa=id_empresa, dias=dias)

    def efetivo_ativo(self, id_empresa: int):
        return self._usuario.efetivo_ativo(id_empresa=id_empresa)

    def engajamento_equipe(self, id_empresa: int, dias: int = 7):
        return self._usuario.engajamento_equipe(id_empresa=id_empresa, dias=dias)

    # --- B1, B2, B4, E3: qualidade da IA ---
    def confianca_media_ia(self, id_empresa: int, dias: int = 30):
        return self._output_bion.confianca_media(id_empresa=id_empresa, dias=dias)

    def completude_media_ia(self, id_empresa: int, dias: int = 30):
        return self._output_bion.completude_media(id_empresa=id_empresa, dias=dias)

    def versoes_ia_em_uso(self, id_empresa: int, dias: int = 30):
        return self._output_bion.versoes_em_uso(id_empresa=id_empresa, dias=dias)

    def correlacao_completude_confianca(self, id_empresa: int, dias: int = 30):
        return self._output_bion.correlacao_completude_confianca(id_empresa=id_empresa, dias=dias)

    # --- C1-C5: epidemiológico ---
    def top_cid_por_regiao(self, id_empresa: int, dias: int = 14, limite: int = 10):
        return self._resultado_prescricao.top_cid_por_regiao(id_empresa=id_empresa, dias=dias, limite=limite)

    def evolucao_cid(self, id_empresa: int, codigo_cid10: str, dias: int = 30):
        return self._resultado_prescricao.evolucao_cid(id_empresa=id_empresa, codigo_cid10=codigo_cid10, dias=dias)

    def incidencia_por_regiao(self, id_empresa: int, dias: int = 14):
        return self._resultado_prescricao.incidencia_por_regiao(id_empresa=id_empresa, dias=dias)

    def tempo_ate_atendimento(self, id_empresa: int, dias: int = 30):
        return self._atendimento.tempo_ate_atendimento(id_empresa=id_empresa, dias=dias)

    def queixas_mais_frequentes(self, id_empresa: int, dias: int = 30, top: int = 15):
        return self._input_protocolo.queixas_mais_frequentes(id_empresa=id_empresa, dias=dias, top=top)

    # --- D1-D4: farmacovigilância ---
    def interacoes_por_gravidade(self):
        return self._interacoes.por_gravidade()

    def alergias_top_substancias(self, id_empresa: int, limite: int = 10):
        return self._alergia.top_substancias(id_empresa=id_empresa, limite=limite)

    def alergia_gravidade_por_substancia(self, id_empresa: int, substancia: str):
        return self._alergia.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)

    def urgencia_exames_por_origem(self, id_empresa: int, dias: int = 30):
        return self._exame.urgencia_por_origem(id_empresa=id_empresa, dias=dias)

    def medicamentos_top_por_classe(self, id_empresa: int, dias: int = 30, limite: int = 10):
        return self._prescricao.top_por_classe(id_empresa=id_empresa, dias=dias, limite=limite)

    def medicamentos_top_principios_por_classe(self, id_empresa: int, classe: str, dias: int = 30, limite: int = 10):
        return self._prescricao.top_principios_ativos_por_classe(
            id_empresa=id_empresa, classe=classe, dias=dias, limite=limite
        )

    # --- E2: pitch executivo ---
    def tendencia_eficiencia(self, id_empresa: int, dias: int = 30):
        return self._atendimento.tendencia_eficiencia(id_empresa=id_empresa, dias=dias)

    # --- F1-F4: histórico clínico do paciente ---
    def doencas_cronicas_top(self, id_empresa: int, limite: int = 10):
        return self._paciente.doencas_cronicas_top(id_empresa=id_empresa, limite=limite)

    def uso_continuo_medicacao(self, id_empresa: int):
        return self._paciente.uso_continuo_medicacao(id_empresa=id_empresa)

    def distribuicao_tipo_sanguineo(self, id_empresa: int):
        return self._paciente.distribuicao_tipo_sanguineo(id_empresa=id_empresa)

    def alergias_gravidade_geral(self, id_empresa: int):
        return self._alergia.gravidade_geral(id_empresa=id_empresa)