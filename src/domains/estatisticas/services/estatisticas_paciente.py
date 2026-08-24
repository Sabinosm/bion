from src.domains.paciente.services import PacienteService as ps


class EstatisticasPaciente:
    def pacientes_cadastrados_hoje(self, id_empresa):
        return ps.contar_pacientes_hoje(id_empresa=id_empresa)
            
    
    def pacientes_cadastrados(self, id_empresa):
        return ps.contar_total_pacientes(id_empresa=id_empresa)
            