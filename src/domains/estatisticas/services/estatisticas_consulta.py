from src.domains.consulta.service import ConsultaService

cs = ConsultaService()


class EstatisticasConsulta:
    
    def consultas_hoje(self, id_empresa):
        return cs.contar_consultas_dia(id_empresa=id_empresa)
