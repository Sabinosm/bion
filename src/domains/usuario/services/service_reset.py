"""Mixin com as rotinas de reset de credenciais do domínio Usuario.

UsuarioService (service.py) herda deste mixin. Requer que a classe que
o utiliza tenha `self.repo` (UsuarioRepository) e `self.buscar_por_uuid`.
"""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError


class ResetCredenciaisMixin:
    """Mixin de reset de credenciais e senha.

    Todos os métodos aqui exigem que o solicitante seja o super admin
    da empresa, e bloqueiam qualquer ação sobre o próprio super admin
    (que nunca pode ter senha/2FA resetados, nem por si mesmo). O alvo
    precisa pertencer à mesma empresa do solicitante -- senão é tratado
    como "não encontrado" (RecursoNaoEncontradoError), não como "acesso
    negado", pra não revelar que o uuid existe em outra empresa.
    """

    def resetar_senha_usuario(
        self,
        uuid_usuario: str,
        id_empresa_solicitante: int,
        solicitante_eh_super_admin: bool = False,
        commit: bool = True
    ):
        """Reseta SÓ a senha de um usuário-alvo, devolvendo-o ao
        onboarding para que ele mesmo defina a nova senha.

        Não existe conceito de "senha temporária" gerada pelo sistema
        -- isso daria ao admin uma senha válida da conta de outra
        pessoa. O reset zera hash_senha; o usuário define a própria
        senha nova, do mesmo jeito que no cadastro inicial. Diferente
        de reset_total: não mexe em WebAuthn nem em status -- só a
        senha, sem forçar o usuário a recadastrar 2FA.

        Parâmetros:
            uuid_usuario: identificador do usuário alvo.
            id_empresa_solicitante: empresa de quem está pedindo (ver
                get_id_empresa_sessao() no controller).
            solicitante_eh_super_admin: se True, quem está pedindo é o
                super admin da empresa.

        Retorno:
            Instância de Usuario atualizada e salva.

        Levanta:
            DadosInvalidosError: se o solicitante não for o super admin,
                ou se o alvo for o próprio super admin.
            RecursoNaoEncontradoError: se o usuário não existir ou não
                pertencer à empresa do solicitante.
        """
        if not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode resetar a senha de um usuário."
            )

        u = self.buscar_por_uuid(uuid_usuario)
        if u.id_empresa != id_empresa_solicitante:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado: {uuid_usuario}")

        if u.is_super_admin:
            raise DadosInvalidosError(
                "O administrador principal não pode ter a senha resetada por outra pessoa."
            )

        u.hash_senha = None
        u.onboarding_pendente = True
        # Derruba qualquer sessão aberta dele nas rotas de leitura
        # sensível (ver requer_senha_atualizada em session.py), mesmo
        # que o onboarding em si já impeça uso normal.
        u.senha_versao = (u.senha_versao or 1) + 1
        return self.repo.save(u, commit=commit)

    def reset_2fa(self, uuid_usuario: str, id_empresa_solicitante: int, solicitante_eh_super_admin: bool = False, commit:bool=True):
        """Reseta o 2FA de um usuário: remove TODAS as credenciais
        WebAuthn cadastradas, forçando o cadastro de um dispositivo novo
        no próximo login. A senha permanece válida.

        Diferente de desativar()/ativar() (onde a trava de super admin
        só entra se o ALVO for admin), aqui a trava é sobre quem
        SOLICITA, sempre -- resetar 2FA de terceiros é sensível por si
        só, mesmo para um usuário sem papel de admin.

        Parâmetros:
            uuid_usuario: identificador do usuário alvo.
            id_empresa_solicitante: empresa de quem está pedindo (ver
                get_id_empresa_sessao() no controller).
            solicitante_eh_super_admin: se True, quem está pedindo é o
                super admin da empresa.

        Retorno:
            Instância de Usuario (para manter o padrão de retorno do
            controller, que chama u.to_dict()).

        Levanta:
            DadosInvalidosError: se o solicitante não for o super admin.
            RecursoNaoEncontradoError: se o usuário não existir ou não
                pertencer à empresa do solicitante.
        """
        if not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode resetar o 2FA de um usuário."
            )

        u = self.buscar_por_uuid(uuid_usuario)
        if u.id_empresa != id_empresa_solicitante:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado: {uuid_usuario}")

        self.repo.remover_credenciais(u.id, commit=commit)
        return u

    def reset_total(self, uuid_usuario: str, id_empresa_solicitante: int, solicitante_eh_super_admin: bool = False, commit: bool = True):
        """Reset completo de credenciais de um usuário: remove o 2FA
        (mesma lógica de reset_2fa) e também zera a senha, devolvendo o
        usuário ao estado de onboarding pendente -- ele precisa refazer
        o fluxo de ativação de conta do zero.

        RESTRIÇÕES: mesmas de reset_2fa (só super admin, só dentro da
        própria empresa), mais uma: o próprio super admin nunca pode ser
        resetado (nem por ele mesmo), mesma lógica de proteção já
        aplicada em desativar().

        Parâmetros:
            uuid_usuario: identificador do usuário alvo.
            id_empresa_solicitante: empresa de quem está pedindo.
            solicitante_eh_super_admin: se True, quem está pedindo é o
                super admin da empresa.

        Retorno:
            Instância de Usuario atualizada e salva.

        Levanta:
            DadosInvalidosError: se o solicitante não for o super admin,
                ou se o alvo for o próprio super admin.
            RecursoNaoEncontradoError: se o usuário não existir ou não
                pertencer à empresa do solicitante.
        """
        if not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode resetar um usuário por completo."
            )

        u = self.buscar_por_uuid(uuid_usuario)
        if u.id_empresa != id_empresa_solicitante:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado: {uuid_usuario}")

        if u.is_super_admin:
            raise DadosInvalidosError("O administrador principal não pode ser resetado.")

        self.repo.remover_credenciais(u.id, commit=commit)
        u.hash_senha = None
        u.onboarding_pendente = True
        u.status = "pendente"
        return self.repo.save(u, commit=commit)