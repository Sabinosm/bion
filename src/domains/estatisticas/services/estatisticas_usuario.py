from src.domains.estatisticas.interpretacao_helper import interpretacao_sem_nivel
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
 
    # --- A5: Engajamento/atividade da equipe ---
    def engajamento_equipe(self, id_empresa, dias=7):
        """Quantidade de profissionais sem acesso ao sistema há mais de N dias.
 
        Grupo 2 -- direcao alto_ruim (mais inativos é pior). comparacao
        NÃO é vs. período anterior aqui (exigiria snapshot histórico de
        quem estava inativo em cada data, que não existe) -- em vez
        disso, comparacao mostra o % de inativos sobre o total de
        profissionais ativos, que já é uma leitura relativa útil.
 
        Retorna: {"total_inativos": int, "dias": int, "profissionais": [...],
                  "leitura": str, "interpretacao": {...}}
        """
        total = us.inativos_ha_dias(id_empresa=id_empresa, dias=dias)
        lista = us.lista_inativos_ha_dias(id_empresa=id_empresa, dias=dias)
 
        leitura = f"{total} profissionais sem acesso ao sistema há mais de {dias} dias"
 
        por_papel = us.efetivo_por_papel(id_empresa=id_empresa)
        total_ativos = sum(por_papel.values())
        comparacao = None
        if total_ativos:
            pct = round((total / total_ativos) * 100, 1)
            comparacao = f"{total} de {total_ativos} profissionais ativos ({pct}%) estão sem acesso há mais de {dias} dias"
 
        interpretacao = interpretacao_sem_nivel(
            texto="Alto = risco de baixa adesão da equipe ao sistema; considerar suporte, treinamento ou revisão de acesso para os profissionais listados",
            direcao="alto_ruim",
            comparacao=comparacao,
        )
 
        return {
            "total_inativos": total,
            "dias": dias,
            "profissionais": [u.to_dict_few() for u in lista],
            "leitura": leitura,
            "interpretacao": interpretacao,
        }