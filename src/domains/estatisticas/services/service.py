from estatisticas_usuario import EstatisticasUsuario as eu
from estatisticas_paciente import EstatisticasPaciente as ep
from estatisticas_consulta import EstatisticasConsulta as ec


class EstatisticasService:
    def estatisticas_geral(self, id_empresa):
        
        estatisticas = {
            "total_profissionais": eu.contagem_profissionais(id_empresa=id_empresa),
            "profissionais_pendentes" : eu.profissonais_status(id_empresa=id_empresa,status="pendente"),
            "profissionais_ativos" :  eu.profissonais_status(id_empresa=id_empresa,status="ativo"),
            "consultas_hoje":ec.consultas_hoje(id_empresa=id_empresa),
            "pacientes_cadastrados": ep.contagem_pacientes_cadastrados(id_empresa=id_empresa)
        }
        
        return estatisticas
        
    
    pass