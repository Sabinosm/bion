"""
sessaoSenha.py

Checagem pontual da versão da senha para LEITURA sensível. Existe uma categoria
intermediária que nem o step-up cobre (não é escrita) nem o prazo de
inatividade da sessão cobre bem sozinho: a leitura de dados clínicos de
paciente. Uma sessão sequestrada poderia continuar lendo prontuário pelo resto
do prazo de inatividade do dono mesmo depois de ele já ter trocado a senha;
pouco tempo, mas dados de saúde justificam fechar essa janela também.

A checagem compara a versão da senha gravada na sessão no momento do login
com a versão atual do banco (1 consulta indexada por PK, só dessa coluna, sem
carregar o usuário inteiro). Se não bater, a tentativa é registrada no log de
acesso negado e a sessão é encerrada, mesmo que ainda estivesse dentro do
prazo. Por custar uma consulta, só roda nas rotas decoradas explicitamente,
nunca no decorator de login, que valeria para todo o tráfego autenticado.

A versão é gravada na sessão em todo login (senha, Google, confirmação de 2FA)
e incrementada no banco toda vez que a senha muda, seja por troca do próprio
usuário ou por reset de um admin.
"""

from flask import session

from src.core.session.sessaoUsuarios import get_id_usuario_sessao, get_id_empresa_sessao, _resposta_erro
from src.core.session.sessaoAutenticacao import _requer_papeis


def _senha_sessao_atualizada(id_usuario: int) -> bool:
    """Compara a versão da senha da sessão (gravada no login) com a atual do banco.

    Returns:
        True se a sessão foi criada com a versão vigente. Também True se a
        sessão não tem a chave (aberta antes deste controle existir): o
        fail-open é intencional, para não deslogar todo mundo só por a chave
        faltar, diferente do fail-closed usado para o super admin. False se a
        senha mudou depois do login, ou se o usuário não existe mais.
    """
    versao_sessao = session.get("senha_versao")
    if versao_sessao is None:
        return True

    from src.domains.usuario.repository import UsuarioRepository
    versao_atual = UsuarioRepository().find_senha_versao(id_usuario)
    return versao_atual is not None and versao_sessao == versao_atual


def _registrar_acesso_negado(id_usuario: int, acao_log: str):
    """Grava o log de acesso negado por senha desatualizada e confirma a transação.

    O registro de auditoria só adiciona o log à sessão do banco, então o commit
    é feito aqui. Uma falha ao gravar o log não impede a negação do acesso: é
    desfeita e apenas registrada no log da aplicação.

    Imports locais para não criar dependência circular entre este módulo
    (usado por praticamente todo domínio) e os de auditoria e banco.
    """
    from flask import request, current_app
    from src.models import db
    from src.domains.auditoria.service import AuditoriaService

    try:
        AuditoriaService().registrar_acesso_negado(
            id_empresa=get_id_empresa_sessao(),
            id_usuario=id_usuario,
            recurso=acao_log,
            operacao="leitura",
            ip_origem=request.headers.get("X-Forwarded-For", request.remote_addr),
            motivo="sessao_com_senha_desatualizada",
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Falha ao registrar acesso negado por senha desatualizada.")


def requer_senha_atualizada(acao_log: str):
    """Decorator para rotas de LEITURA de dados sensíveis (dados clínicos de paciente).

    Além da checagem normal de sessão (login, onboarding e 2FA), confere se a
    senha do usuário não mudou desde que ESTA sessão foi criada. Se mudou,
    registra a tentativa, encerra a sessão e nega, mesmo que a sessão ainda
    estivesse válida para o resto do sistema.

    Diferente de `@acao_sensivel` (escrita, com o contrato (resposta, detalhes)
    para o log de mutação) e do step-up (exige reautenticação ATIVA antes de
    agir): este não pede nada ao usuário, só verifica passivamente e registra
    quando nega. Pensado para GET.

    Uso:
        @bp.get("/<uuid>/dados-clinicos")
        @requer_senha_atualizada("acesso_dados_clinicos")
        def dados_clinicos(uuid):
            ...

    Args:
        acao_log: identificador gravado no log como recurso acessado quando o
            acesso é negado.

    Returns:
        Decorator que envolve a view e responde 403
        `sessao_invalida_senha_alterada` quando a checagem falha.
    """
    def verificar():
        id_usuario = get_id_usuario_sessao()
        if _senha_sessao_atualizada(id_usuario):
            return None

        _registrar_acesso_negado(id_usuario, acao_log)
        session.clear()
        return _resposta_erro(
            "sessao_invalida_senha_alterada",
            "Sua senha foi alterada. Faça login novamente.",
            403,
        )

    return _requer_papeis(verificar)