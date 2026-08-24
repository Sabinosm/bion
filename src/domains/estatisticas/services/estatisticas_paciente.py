from src.domains.paciente.services import PacienteService

ps = PacienteService()


class EstatisticasPaciente:
    def pacientes_cadastrados_hoje(self, id_empresa):
        return ps.count_pacientes_hoje(id_empresa=id_empresa)
               
    def pacientes_cadastrados(self, id_empresa):
        return ps.count_pacientes(id_empresa=id_empresa)
            