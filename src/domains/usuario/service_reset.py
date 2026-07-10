"""
Mixin com as rotinas de reset de credenciais do dominio Usuario.

Extraido de service.py -- reset_2fa e reset_total nao mudam desde o
original, so foram movidos para cá para reduzir o tamanho do arquivo
principal. UsuarioService herda deste mixin.
"""

from flask import jsonify, session


class ResetCredenciaisMixin:
    """Requer que a classe que usa este mixin tenha `self.repo`
    (UsuarioRepository) com o metodo `find_by_uuid`."""

    def reset_2fa(self, uuid):
        from src.models.usuarios import CredencialWebAuthn
        from src.models import db
        """
        Remove todas as credenciais WebAuthn do usuário. Próximo login dele
        (via senha) vai cair em mfa_pendente, mas sem credencial cadastrada —
        então precisamos tratar esse caso: sessão fica numa espécie de
        'onboarding parcial' só pra recadastrar o WebAuthn.
        """
        usuario = self.repo.find_by_uuid(uuid)

        if not usuario:
            return jsonify({"erro": "usuario_nao_encontrado"}), 404

        # Confere que o admin só reseta usuário da própria empresa
        if usuario.uuid_empresa != session.get("uuid_empresa"):
            return jsonify({"erro": "acesso_negado"}), 403

        CredencialWebAuthn.query.filter_by(uuid_usuario=uuid).delete()

        # Reaproveita o mesmo campo de onboarding: assim o próximo login força
        # a passar pela etapa de cadastro de WebAuthn novamente (senha permanece)
        usuario.onboarding_pendente = True
        db.session.commit()

        return jsonify({"status": "2fa_resetado", "uuid_usuario": uuid}), 200

    def reset_total(self, uuid):
        from src.models.usuarios import CredencialWebAuthn
        from src.models import db

        """
        Reset mais drástico: invalida a senha também. Usuário precisa passar
        pelo fluxo inteiro de novo (Google -> definir senha -> WebAuthn).
        Útil se há suspeita de conta comprometida, não só dispositivo perduzido.
        """
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