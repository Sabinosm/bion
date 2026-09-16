"""Rotas de login/logout do domínio Auth.

A sessão é lida e escrita via cookie httpOnly.

ALTERADO (2FA sempre obrigatório -- ver mfa.py, oauth.py, onboarding.py):
não existe mais login por senha sem 2FA. Todo usuário tem WebAuthn
e/ou TOTP cadastrado obrigatoriamente desde o onboarding, então a
sessão SEMPRE fica pendente (`mfa_pendente=True`) após autenticar por
senha -- `id_empresa` só é liberado depois da confirmação via
`/webauthn/2fa/confirmar` ou `/totp/2fa/confirmar` (ver
webauthn_2fa.py e totp_2fa.py). A antiga condição `if tem_2fa` (que
dependia de o usuário ter ou não credencial WebAuthn) foi substituída
por `metodo_2fa_preferencial`, que só decide QUAL método oferecer
primeiro -- ver mfa.py.

ALTERADO (múltiplos admins por empresa):
- `session["is_super_admin"]` passa a ser gravado aqui, junto dos
  demais dados de sessão -- é o que `g.is_super_admin` (session.py) lê
  depois em toda rota autenticada. Sem isso, o super admin perderia o
  poder de criar/alterar outros admins mesmo logado corretamente.

ADICIONADO (checagem de sessão obsoleta em leituras sensíveis -- ver
requer_senha_atualizada em session.py):
- `session["senha_versao"]` passa a ser gravada aqui, junto dos demais
  dados -- é o snapshot que as rotas de leitura sensível comparam
  contra o valor atual do banco.

DECISÃO (reset de senha por admin -- ver resetar_senha_usuario em
service.py): não existe estado "senha temporária pendente" separado.
Um reset de admin simplesmente zera hash_senha e marca
onboarding_pendente=True -- reaproveitando 100% do branch de
onboarding que já existe abaixo. O usuário reseta e o próximo login
dele já cai natural em "onboarding_pendente", exatamente como cairia
se fosse uma conta nova sem senha definida ainda. Nenhuma lógica nova
precisou entrar aqui por causa disso.

Nota sobre reset de senha + 2FA já cadastrado: se o admin resetar a
senha de um usuário que já tem WebAuthn/TOTP confirmados, esses
fatores de 2FA NÃO são apagados -- só a senha. O próximo login cai em
onboarding_pendente (definir senha nova), mas onboarding.py::concluir
já vê que o usuário tem 2FA confirmado e libera a sessão sem pedir
para escolher de novo (ver onboarding.py, _usuario_tem_algum_2fa_confirmado).
"""

from flask import Blueprint, request, session
from src.core.responses import json_success, json_error
from src.models import db
from src.domains.auth.mfa import metodo_2fa_preferencial, metodos_2fa_disponiveis
from src.domains.auth.onboarding import _usuario_tem_algum_2fa_confirmado
from .services import AuthService


bp = Blueprint("auth", __name__)
_svc = AuthService()


class Login():
    
    @staticmethod    
    @bp.post("/login")
    def login():
        """Autentica um usuário por login e senha.

        ALTERADO: a sessão SEMPRE fica pendente de 2FA após autenticar
        por senha -- não existe mais caminho de login sem 2FA (ver
        docstring do módulo).

        Corpo esperado (JSON ou form): `user_login`, `senha`.

        Retorno:
            200 com `status: mfa_pendente` se autenticado (sempre o
                caso, exceto onboarding pendente).
            200 com `status: onboarding_pendente` se o usuário não tem
                senha definida ainda -- inclusive logo após um reset de
                senha feito por um admin (ver resetar_senha_usuario em
                service.py), que reaproveita este mesmo estado.
            400 se o usuário só tiver login via Google (sem senha).
            401 se as credenciais forem inválidas.
            422 se login ou senha não forem enviados.
        """
        
        data = request.get_json(silent=True) or request.form.to_dict()
        login_val = (data.get("user_login") or "").strip()
        senha = data.get("senha") or ""

        if not login_val or not senha:
            return json_error("Login e senha são obrigatórios.", 422)
        
        usuario, motivo = _svc.autenticar(login_val, senha)
        
        if motivo == "sem_senha":
            return json_error("Usuário sem senha, faça login pelo Google.", 400)
        if not usuario:
            return json_error("Credenciais inválidas.", 401)

        # ALTERADO (2FA sempre obrigatório): não decide mais "se" pedir
        # 2FA, só "qual" método oferecer primeiro -- ver mfa.py. `None`
        # só ocorreria para uma conta legada sem nenhum fator migrado
        # (não deveria existir depois do onboarding atual); nesse caso
        # o frontend tenta WebAuthn e cai para TOTP normalmente (ver
        # afterLogin.js), e se o usuário não tiver nenhum dos dois de
        # verdade, os dois passos falham e o login fica bloqueado --
        # correto para uma conta inconsistente.
        metodo = metodo_2fa_preferencial(usuario.id)

        session.clear()
        session.permanent = True
        session["id_usuario"] = usuario.id
        # ALTERADO (assertivo, sem alias): session["tipo_usuario"] saiu.
        # Duas chaves independentes entram no lugar — is_admin e
        # funcao_clinica podem ambos ser "verdadeiros" ao mesmo tempo
        # (admin que também atende). Ver session.py para os decorators
        # que leem cada uma separadamente.
        session["is_admin"] = usuario.is_admin
        session["funcao_clinica"] = usuario.funcao_clinica
        session["uuid_usuario"] = usuario.uuid
        # ADICIONADO: necessário pra g.is_super_admin (session.py) e
        # pra requer_super_admin funcionarem em rotas futuras nesta sessão.
        session["is_super_admin"] = usuario.is_super_admin
        # ADICIONADO (checagem de sessão obsoleta em leituras sensíveis
        # -- ver requer_senha_atualizada em session.py): snapshot da
        # versão da senha NO MOMENTO deste login. Se a senha mudar
        # depois (autotroca ou reset por admin), essa sessão fica com
        # um valor antigo e é pega pela checagem nas rotas decoradas.
        session["senha_versao"] = usuario.senha_versao
        
        
        if usuario.onboarding_pendente:
            # CORRIGIDO: `onboarding_pendente` só virava False dentro
            # de /onboarding/concluir -- uma chamada HTTP separada da
            # confirmação do 2FA em si. Se a sessão caísse entre o TOTP/
            # WebAuthn ser confirmado (persistido, isso não se perde) e
            # essa chamada, o usuário ficava com onboarding_pendente
            # preso em True para sempre no banco, mesmo já tendo senha e    
            # 2FA prontos -- e o próximo login o jogava de volta para
            # onboarding.js, que podia acabar reiniciando o cadastro de
            # 2FA (ver /totp/registrar/iniciar) mesmo já havendo um
            # confirmado. Aqui fechamos o onboarding no próprio login
            # quando os pré-requisitos já estão de fato satisfeitos, em
            # vez de depender só daquela chamada separada ter ocorrido.
            if usuario.hash_senha and _usuario_tem_algum_2fa_confirmado(usuario.id):
                usuario.onboarding_pendente = False
                db.session.commit()
                # segue para o fluxo normal abaixo (mfa_pendente) --
                # não retorna aqui.
            else:
                session["onboarding_pendente"] = True
                return json_success(
                    data={"status": "onboarding_pendente"},
                    message="Cadastro incompleto, finalize o onboarding.",
                )

        # ALTERADO: sempre mfa_pendente agora -- não há mais o ramo
        # `_svc.load(usuario)` que liberava a sessão direto sem 2FA.
        session["mfa_pendente"] = True
        return json_success(
            data={
                "status": "mfa_pendente",
                "metodo": metodo,  # pode ser None -- ver metodos abaixo
                "metodos_disponiveis": metodos_2fa_disponiveis(usuario.id),
            },
            message="Confirmação adicional necessária.",
        )
    
            
    @staticmethod
    @bp.post("/logout")
    def logout():
        """Encerra a sessão atual.

        Retorno:
            200 confirmando o encerramento.
        """
        session.clear()
        return json_success(message="Sessão encerrada.")