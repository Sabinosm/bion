from .estatisticas_usuario import EstatisticasUsuario
from .estatisticas_paciente import EstatisticasPaciente
from .estatisticas_consulta import EstatisticasConsulta
from .estatisticas_atendimento import EstatisticasAtendimento

eu = EstatisticasUsuario()
ep = EstatisticasPaciente()
ec = EstatisticasConsulta()
ea = EstatisticasAtendimento()


class EstatisticasService:

    # Mantido para compatibilidade com quem já usa /geral (ex: primeiro
    # carregamento do dashboard). Continua leve -- só chama os métodos
    # 🟢 instantâneos, sem os cards mais pesados/detalhados.
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