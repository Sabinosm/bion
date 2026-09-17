"""
sessaoSenha.py -- Checagem pontual de senha_versao para LEITURA sensível.

Existe uma categoria intermediária que nem o step-up cobre (não é
escrita) nem o TTL de inatividade da sessão cobre bem o bastante
sozinho: LEITURA de dados clínicos de paciente. Uma sessão sequestrada
pode continuar lendo prontuário por até o TTL de inatividade real do
dono mesmo depois de ele já ter trocado a senha -- pouco tempo, mas
dados de saúde justificam fechar essa janela também.

`requer_senha_atualizada(acao_log)` cobre isso: 1 SELECT indexado por
PK (só a coluna `senha_versao`, via
`UsuarioRepository.find_senha_versao` -- não carrega o Usuario
inteiro), aplicado só nas rotas decoradas explicitamente, nunca em
requer_login. Se a versão gravada na sessão no momento do login não
bate com a atual do banco, a tentativa é logada e a sessão é encerrada
(403) -- mesmo que ainda estivesse dentro do TTL.

`senha_versao` é gravada na sessão em TODO login (senha, Google,
confirmação de 2FA -- ver login.py e oauth.py) e incrementada no banco
toda vez que `hash_senha` muda (troca pelo próprio usuário ou reset
por admin -- ver service.py e usuario.py).
"""

from functools import wraps
from flask import session, jsonify

from src.core.sessaoHelpers.sessaoUsuarios import get_id_usuario_sessao, _popula_g
from src.core.sessaoHelpers.sessaoAutenticacao import _checagem_base_sessao


def _senha_sessao_atualizada(id_usuario: int) -> bool:
    """Compara senha_versao gravada na sessão (no login) contra o valor
    ATUAL no banco. Custa 1 SELECT indexado por PK, de uma única
    coluna -- por isso não entra em `_popula_g`/`requer_login` (rodaria
    em 100% do tráfego autenticado); é chamada só de dentro de
    `requer_senha_atualizada`, nas rotas que o time decidir decorar.

    Retorno: True se a sessão foi criada com a senha_versao vigente
    (ou se a sessão ainda não tem essa chave -- sessão aberta antes
    deste deploy; fail-open aqui é intencional pra não deslogar todo
    mundo no dia do deploy só por essa checagem faltar, diferente do
    fail-closed usado para is_super_admin). False se a senha mudou
    depois deste login.
    """
    versao_sessao = session.get("senha_versao")
    if versao_sessao is None:
        return True

    from src.domains.usuario.repository import UsuarioRepository
    versao_atual = UsuarioRepository().find_senha_versao(id_usuario)
    return versao_atual is not None and versao_sessao == versao_atual


def requer_senha_atualizada(acao_log: str):
    """Decorator para rotas de LEITURA de dados sensíveis (dados
    clínicos de paciente). Além da checagem normal de sessão (login +
    onboarding + mfa), confere se a senha do usuário não mudou desde
    que ESTA sessão foi criada. Se mudou, a sessão é tratada como
    obsoleta para esse tipo de acesso -- registra a tentativa e nega,
    mesmo que a sessão continue dentro do TTL normal e válida para o
    resto do sistema.

    Diferente de `@acao_sensivel` (usado em rotas de ESCRITA, com o
    contrato de (resposta, detalhes) para log de mutação) e diferente
    de `@StepUp.requer_confirmacao_recente` (exige reautenticação ATIVA
    antes de agir): este decorator não pede nada ao usuário, só
    verifica passivamente e loga quando nega -- pensado pra GET.

    Uso:
        @bp.get("/<uuid>/dados-clinicos")
        @requer_senha_atualizada("acesso_dados_clinicos")
        def dados_clinicos(uuid):
            ...

    Parâmetros:
        acao_log: identificador gravado no log quando o acesso é
            negado por sessão com senha desatualizada.

    Retorno:
        Decorator que envolve a view, retornando 403 com
        `sessao_invalida_senha_alterada` quando a checagem falha.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            erro = _checagem_base_sessao()
            if erro:
                return erro

            id_usuario = get_id_usuario_sessao()
            if not _senha_sessao_atualizada(id_usuario):
                # Log da tentativa negada. Import local para não criar
                # dependência circular entre este módulo (usado por
                # praticamente todo domínio) e o módulo de auditoria.
                from src.domains.auditoria.service import AuditoriaService
                au = AuditoriaService()

                au.registrar_acesso_negado(
                    id_usuario=id_usuario,
                    acao=acao_log,
                    motivo="sessao_com_senha_desatualizada",
                )
                session.clear()
                return jsonify({"erro": "sessao_invalida_senha_alterada"}), 403

            _popula_g()
            return f(*args, **kwargs)
        return wrapper
    return decorator