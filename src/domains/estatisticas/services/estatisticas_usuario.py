from src.domains.usuario.services.service import UsuarioService

us = UsuarioService()


class EstatisticasUsuario:
    def contagem_profissionais(self, id_empresa):
        return us.contagem_profissionais(id_empresa=id_empresa)

    def profissonais_status(self, id_empresa, status):
        return us.contagem_profissionais_por_status(id_empresa=id_empresa, status=status)

    # --- A4: Efetivo ativo por papel ---
    def efetivo_ativo(self, id_empresa):
        """Contagem de usuários ativos por papel (médico, enfermeiro, admin).

        Retorna: {"por_papel": {papel: total, ...}, "leitura": str}
        """
        por_papel = us.efetivo_por_papel(id_empresa=id_empresa)

        # monta a leitura só com os papéis presentes, na ordem
        # medico -> enfermeiro -> admin (ordem de prioridade de leitura)
        partes = []
        for papel, rotulo in (("medico", "médicos"), ("enfermeiro", "enfermeiros"), ("admin", "admins")):
            if por_papel.get(papel):
                partes.append(f"{por_papel[papel]} {rotulo}")

        leitura = f"Equipe ativa: {', '.join(partes)}" if partes else "Nenhum profissional ativo no momento"

        return {"por_papel": por_papel, "leitura": leitura}