"""Mixin com as rotinas de reset de credenciais do domínio Usuario.

CORRIGIDO: este mixin não está mais em uso -- UsuarioService (service.py)
agora define reset_2fa/reset_total diretamente na classe, o que tem
prioridade sobre este mixin no MRO do Python. Ainda assim, corrigido
para não ficar código morto E COM BUGS no repositório:

  - `CredencialWebAuthn.query.filter_by(uuid_usuario=uuid)` -- o model
    (credencial_webauthn.py) não tem coluna `uuid_usuario`, tem
    `id_usuario` (BigInteger, FK). Essa query quebraria em runtime.
  - `usuario.uuid_empresa` -- Usuario não expõe esse atributo; tem
    `id_empresa` (coluna) e `empresa` (relationship). Substituído pela
    comparação de id_empresa, seguindo o mesmo padrão usado no resto
    do domínio (get_id_empresa_sessao(), não get_uuid_empresa_sessao()).

Mantido aqui só como referência/histórico. Se algum dia isso for
reativado (ex.: reverter a decisão de colocar os métodos direto em
UsuarioService), a versão de service.py é a que reflete as decisões
mais recentes (isolamento por empresa, trava de super admin, proteção
do próprio super admin em reset_total) e deveria ser a fonte de
verdade -- não este arquivo.
"""

from flask import jsonify
from src.core.session import get_id_empresa_sessao


class ResetCredenciaisMixin:
    """Mixin de reset de credenciais.

    Requer que a classe que o utiliza tenha `self.repo` (UsuarioRepository)
    com os métodos `find_by_uuid` e `remover_credenciais_webauthn`.
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
        from src.models import db

        usuario = self.repo.find_by_uuid(uuid)

        if not usuario:
            return jsonify({"erro": "usuario_nao_encontrado"}), 404
        if usuario.id_empresa != get_id_empresa_sessao():
            return jsonify({"erro": "acesso_negado"}), 403

        # CORRIGIDO: era CredencialWebAuthn.query.filter_by(uuid_usuario=uuid)
        # -- coluna inexistente (o model usa id_usuario, BigInteger).
        # Delega pro repository, que já centraliza essa query (usada
        # também por UsuarioService.reset_2fa em service.py).
        self.repo.remover_credenciais_webauthn(usuario.id)

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
        from src.models import db

        usuario = self.repo.find_by_uuid(uuid)
        if not usuario:
            return jsonify({"erro": "usuario_nao_encontrado"}), 404

        if usuario.id_empresa != get_id_empresa_sessao():
            return jsonify({"erro": "acesso_negado"}), 403

        self.repo.remover_credenciais_webauthn(usuario.id)
        usuario.hash_senha = None
        usuario.onboarding_pendente = True
        db.session.commit()

        return jsonify({"status": "reset_completo", "uuid_usuario": uuid}), 200