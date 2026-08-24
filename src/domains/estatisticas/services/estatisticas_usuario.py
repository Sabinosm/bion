from src.domains.usuario.services.service import UsuarioService as us


class EstatisticasUsuario:
    def contagem_profissionais(self, id_empresa):
        us.contagem_profissionais(id_empresa=id_empresa)
        pass

    def profissonais_status(self, id_empresa, status):
        us.contagem_profissionais_por_status(id_empresa=id_empresa,status=status)
        pass
