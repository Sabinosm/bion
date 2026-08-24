from src.domains.usuario.services.service import UsuarioService

us = UsuarioService()


class EstatisticasUsuario:
    def contagem_profissionais(self, id_empresa):
        return us.contagem_profissionais(id_empresa=id_empresa)


    def profissonais_status(self, id_empresa, status):
        return us.contagem_profissionais_por_status(id_empresa=id_empresa,status=status)
        
