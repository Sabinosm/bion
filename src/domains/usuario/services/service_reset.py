"""Mixin com as rotinas de reset de credenciais do domínio Usuario."""

from flask import jsonify, session


class ResetCredenciaisMixin:
    """Mixin de reset de credenciais.

    Requer que a classe que o utiliza tenha `self.repo` (UsuarioRepository)
    com o método `find_by_uuid`.
    """

    def reset_2fa(self, uuid):
        """Remove as credenciais WebAuthn do usuário, forçando recadastro.

        A senha do usuário permanece válida. No próximo login ele cairá
        em estado de "onboarding pendente" apenas para recadastrar o
        WebAuthn, já que não haverá credencial 2FA registrada.

        Parâmetros:
            uuid: identificador do usuário a ser resetado.

        Retorno:
            Tupla (response JSON, status HTTP). 404 se o usuário não
            existir; 403 se pertencer a outra empresa; 200 em sucesso.
        """
        from src.models.usuarios import CredencialWebAuthn
        from src.models import db

        usuario = self.repo.find_by_uuid(uuid)

        if not usuario:
            return jsonify({"erro": "usuario_nao_encontrado"}), 404

        if usuario.uuid_empresa != session.get("uuid_empresa"):
            return jsonify({"erro": "acesso_negado"}), 403

        CredencialWebAuthn.query.filter_by(uuid_usuario=uuid).delete()

        usuario.onboarding_pendente = True
        db.session.commit()

        return jsonify({"status": "2fa_resetado", "uuid_usuario": uuid}), 200

    def reset_total(self, uuid):
        """Reset completo de credenciais: invalida senha e WebAuthn.

        Mais drástico que `reset_2fa`: o usuário precisa refazer todo o
        fluxo de acesso (login social -> definir senha -> WebAuthn).
        Indicado em casos de suspeita de conta comprometida.

        Parâmetros:
            uuid: identificador do usuário a ser resetado.

        Retorno:
            Tupla (response JSON, status HTTP). 404 se o usuário não
            existir; 403 se pertencer a outra empresa; 200 em sucesso.
        """
        from src.models.usuarios import CredencialWebAuthn
        from src.models import db

        usuario = self.repo.find_by_uuid(uuid)
        if not usuario:
            return jsonify({"erro": "usuario_nao_encontrado"}), 404

        if usuario.uuid_empresa != session.get("uuid_empresa"):
            return jsonify({"erro": "acesso_negado"}), 403

        CredencialWebAuthn.query.filter_by(uuid_usuario=uuid).delete()
        usuario.hash_senha = None
        usuario.onboarding_pendente = True
        db.session.commit()

        return jsonify({"status": "reset_completo", "uuid_usuario": uuid}), 200