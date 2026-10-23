"""service_reset.py -- rotinas de reset de credenciais de usuário.

Agrupa, em um mixin herdado pelo service principal, as operações em que o
administrador principal devolve a conta de outra pessoa a um estado de
onboarding: só a senha, só o 2º fator, ou ambos. Nenhuma delas gera
credencial temporária; o próprio usuário define a nova no próximo login.
Requer que a classe que o usa tenha `repo` (UsuarioRepository) e
`buscar_por_uuid_da_empresa`.
"""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError


class ResetCredenciaisMixin:
    """Resets de credenciais feitos pelo super admin sobre usuários da
    própria empresa.

    Todos exigem que o solicitante seja o super admin. Um alvo de outra
    empresa é tratado como "não encontrado" (e não como "acesso negado")
    para não revelar que o uuid existe. Resetar a senha e resetar por
    completo e só o 2FA recusam o próprio super admin como alvo.
    """

    def resetar_senha_usuario(
        self,
        uuid_usuario: str,
        id_empresa_solicitante: int,
        solicitante_eh_super_admin: bool = False,
        commit: bool = True,
    ):
        """Zera só a senha do alvo e o devolve ao onboarding.

        2FA e status permanecem. Incrementa senha_versao, derrubando
        sessões abertas nas rotas protegidas por `requer_senha_atualizada`.

        Parâmetros:
            uuid_usuario: usuário alvo.
            id_empresa_solicitante: empresa de quem pede.
            solicitante_eh_super_admin: se quem pede é o super admin.
            commit: se False, só faz flush (o commit fica com quem chama).

        Retorno:
            Instância de Usuario atualizada.

        Levanta:
            DadosInvalidosError: solicitante não é super admin, ou alvo é
                o próprio super admin.
            RecursoNaoEncontradoError: alvo inexistente ou de outra empresa.
        """
        if not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode resetar a senha de um usuário."
            )

        u = self.buscar_por_uuid_da_empresa(uuid_usuario, id_empresa_solicitante)

        if u.is_super_admin:
            raise DadosInvalidosError(
                "O administrador principal não pode ter a senha resetada por outra pessoa."
            )

        u.hash_senha = None
        u.senha_versao = (u.senha_versao or 1) + 1
        # Sem onboarding_pendente o login não encaminharia o usuário ao
        # fluxo de definição de senha.
        u.onboarding_pendente = True
        return self.repo.save(u, commit=commit)

    def reset_2fa(
        self,
        uuid_usuario: str,
        id_empresa_solicitante: int,
        solicitante_eh_super_admin: bool = False,
        commit: bool = True,
    ):
        """Remove todas as credenciais de 2º fator do alvo (WebAuthn e
        TOTP), forçando o cadastro de um novo método. A senha permanece.

        Diferente de ativar/desativar (cuja trava depende de o ALVO ser
        admin), aqui a trava é sempre sobre quem SOLICITA.

        Parâmetros:
            uuid_usuario: usuário alvo.
            id_empresa_solicitante: empresa de quem pede.
            solicitante_eh_super_admin: se quem pede é o super admin.
            commit: se False, só faz flush, preservando a atomicidade
                esperada por @acao_sensivel.

        Retorno:
            Instância de Usuario atualizada.

        Levanta:
            DadosInvalidosError: solicitante não é super admin, ou alvo é
                o próprio super admin.
            RecursoNaoEncontradoError: alvo inexistente ou de outra empresa.
        """
        if not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode resetar o 2FA de um usuário."
            )

        u = self.buscar_por_uuid_da_empresa(uuid_usuario, id_empresa_solicitante)

        if u.is_super_admin:
            raise DadosInvalidosError(
                "O administrador principal não pode ter o 2FA resetado por outra pessoa."
            )

        self.repo.remover_credenciais(u.id, commit=commit)
        # O login/oauth só consideram o onboarding concluído com senha E
        # 2FA; sem esta flag o usuário nunca seria reconduzido ao cadastro
        # de um novo método.
        u.onboarding_pendente = True
        return self.repo.save(u, commit=commit)

    def reset_total(
        self,
        uuid_usuario: str,
        id_empresa_solicitante: int,
        solicitante_eh_super_admin: bool = False,
        commit: bool = True,
    ):
        """Remove o 2FA e zera a senha do alvo, deixando-o 'pendente' para
        refazer a ativação de conta do zero. Incrementa senha_versao
        (a senha foi zerada); reset_2fa não incrementa, pois a senha
        permanece válida.

        Parâmetros:
            uuid_usuario: usuário alvo.
            id_empresa_solicitante: empresa de quem pede.
            solicitante_eh_super_admin: se quem pede é o super admin.
            commit: se False, só faz flush (o commit fica com quem chama).

        Retorno:
            Instância de Usuario atualizada.

        Levanta:
            DadosInvalidosError: solicitante não é super admin, ou alvo é
                o próprio super admin.
            RecursoNaoEncontradoError: alvo inexistente ou de outra empresa.
        """
        if not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode resetar um usuário por completo."
            )

        u = self.buscar_por_uuid_da_empresa(uuid_usuario, id_empresa_solicitante)

        if u.is_super_admin:
            raise DadosInvalidosError("O administrador principal não pode ser resetado.")

        self.repo.remover_credenciais(u.id, commit=commit)
        u.hash_senha = None
        u.senha_versao = (u.senha_versao or 1) + 1
        u.status = "pendente"
        u.onboarding_pendente = True  # senha e 2FA zerados: reflete isso além do status
        return self.repo.save(u, commit=commit)