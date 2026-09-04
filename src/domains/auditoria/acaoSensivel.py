"""Decorators de auditoria: `acao_sensivel` e `acesso_auditado`.

Dois decorators, para dois casos de uso deliberadamente diferentes:

- `acao_sensivel`: para ESCRITA/EXCLUSÃO. Exige step-up (reconfirmação
  de identidade) antes de rodar a view, e registra `LogAlteracao` de
  forma ATÔMICA com a própria alteração -- ou os dois são persistidos
  juntos, ou nenhum é (ver seção "Atomicidade" abaixo).

- `acesso_auditado`: para LEITURA sensível (ex: abrir um prontuário).
  Não exige step-up -- a sessão autenticada já é suficiente para ler;
  pedir reconfirmação em toda leitura seria fricção sem ganho real de
  segurança. Só registra `LogAcesso` depois que a view responde com
  sucesso.

Por que só `acao_sensivel` tem step-up e ambos têm log
---------------------------------------------------------
Decisão de produto: reconfirmação de identidade fica reservada para
ações destrutivas/irreversíveis, para não gerar fricção nem volume de
registros de step-up desnecessário em cada leitura. Auditoria (o log
em si) continua acontecendo nos dois casos, porque saber "quem viu o
quê e quando" tem valor de compliance mesmo sem reconfirmação.

Atomicidade (ação sensível)
------------------------------
Antes desta versão, `LogAcessoRepository.save()` /
`LogAlteracaoRepository.save()` faziam `db.session.commit()` por conta
própria -- e a view, presumivelmente, já tinha commitado a alteração
antes de chegar aqui. Duas transações separadas = janela onde uma
pode ter sucesso e a outra falhar (ex: a exclusão do prontuário
commita, mas a gravação do log falha por erro de conexão logo depois
-- resultado: ação real sem rastro nenhum na auditoria).

Correção: o repository de auditoria não commita mais sozinho (só
`db.session.add`). Este decorator explicitamente NÃO deixa a view
commitar sozinha também -- a view deve fazer suas alterações via
`db.session.add(...)` / métodos de repository que não commitam, e
DEVOLVER os detalhes; o commit final (que persiste alteração + log
juntos) é feito aqui, uma vez só, no fim do wrapper. Se qualquer parte
falhar (a view lança exceção, o registro do log lança exceção, ou
`registrar_alteracao` recusa por falta de justificativa em DELETE), o
decorator faz `db.session.rollback()` -- a alteração real nunca fica
meio-persistida sem o log correspondente, e vice-versa.

Isso significa que views usadas com `acao_sensivel` PRECISAM parar de
chamar `db.session.commit()` internamente -- se a view já commita
sozinha, a atomicidade descrita aqui deixa de valer (o commit da view
já efetivou a alteração antes do decorator sequer tentar logar). Ver
nota em cada view ao migrar.

Correção de bug -- operacao de LogAcesso
--------------------------------------------
`acesso_auditado` deixou de ter `operacao="leitura"` como default
silencioso. Motivo: o decorator era aplicado igual em views de
leitura e de escrita/exportacao, e quem esquecesse de passar
`operacao` explicitamente na view acabava registrando tudo como
"leitura" mesmo quando o recurso foi exportado ou alterado por uma
rota que nao usa `acao_sensivel`. Agora `operacao` e obrigatorio no
decorator (`@acesso_auditado(recurso, operacao=...)`), forcando quem
aplica o decorator a declarar a natureza real do acesso.
"""

from functools import wraps

from flask import request

from src.models import db
from src.domains.auth.step_up import StepUp
from src.domains.auditoria.service import AuditoriaService
from src.core.session import get_id_usuario_sessao, get_id_empresa_sessao

_auditoria = AuditoriaService()

_OPERACOES_LOG_ACESSO = ("leitura", "escrita", "exclusao-logica", "exportacao")


def _ip_origem():
    # X-Forwarded-For só é confiável se o app estiver atrás de um proxy
    # reverso configurado para sobrescrever request.remote_addr (ex:
    # ProxyFix). Caso contrário, usar request.remote_addr puro --
    # ajustar conforme a infra real.
    return request.headers.get("X-Forwarded-For", request.remote_addr)


def _extrair_resposta_e_detalhes(resultado):
    """Views podem retornar só a resposta Flask, ou (resposta, detalhes)."""
    if isinstance(resultado, tuple) and len(resultado) == 2 and isinstance(resultado[1], dict):
        return resultado
    return resultado, {}


# ======================================================================
# acao_sensivel -- ESCRITA/EXCLUSÃO: step-up obrigatório + log atômico
# ======================================================================

def acao_sensivel(acao, *, tabela):
    """Decorator: exige step-up recente, roda a view, e commita
    alteração + log numa única transação (tudo ou nada).

    Parâmetros:
        acao: identificador da ação sensível (mesmo valor usado no
            frontend em `pedirConfirmacao(acao)`), ex: "editar_paciente".
            Além de disparar o step-up, agora também é persistido na
            coluna `acao` de LogAlteracao -- permite filtrar/pesquisar
            a trilha por ação de negócio, não só por tabela+operação.
        tabela: nome da tabela de origem (`tabela_origem` default se a
            view não especificar um diferente em `detalhes`).

    A view decorada deve:
      - fazer suas alterações via `db.session.add(...)` SEM chamar
        `db.session.commit()` ela mesma;
      - retornar `(resposta_flask, detalhes)`, onde `detalhes` é um
        dict com pelo menos `id_registro` e `uuid_registro` (e
        opcionalmente `operacao`, `tabela_origem`, `campo_alterado`,
        `valor_anterior`, `valor_novo`, `justificativa` -- esta última
        OBRIGATÓRIA quando `operacao` for `"DELETE"`, ou o service
        recusa a operação inteira via rollback).

    Se a view lançar exceção, se faltar `id_registro`/`uuid_registro`
    em `detalhes`, ou se for um DELETE sem `justificativa`, a
    transação inteira sofre rollback -- nenhuma alteração parcial fica
    persistida.
    """
    if not tabela:
        raise ValueError(f"acao_sensivel({acao!r}) exige o parâmetro 'tabela'")

    confirmar_identidade = StepUp.requer_confirmacao_recente(acao)

    def decorator(f):
        @wraps(f)
        @confirmar_identidade
        def wrapper(*args, **kwargs):
            try:
                resultado = f(*args, **kwargs)
                resposta, detalhes = _extrair_resposta_e_detalhes(resultado)

                if "id_registro" not in detalhes or "uuid_registro" not in detalhes:
                    raise ValueError(
                        f"acao_sensivel({acao!r}): a view precisa retornar "
                        f"(resposta, {{'id_registro': ..., 'uuid_registro': ..., ...}})"
                    )

                _auditoria.registrar_alteracao(
                    id_empresa=get_id_empresa_sessao(),
                    acao=acao,
                    tabela_origem=detalhes.get("tabela_origem", tabela),
                    id_registro=detalhes["id_registro"],
                    uuid_registro=detalhes["uuid_registro"],
                    operacao=detalhes.get("operacao", "UPDATE"),
                    id_usuario=get_id_usuario_sessao(),
                    campo_alterado=detalhes.get("campo_alterado"),
                    valor_anterior=detalhes.get("valor_anterior"),
                    valor_novo=detalhes.get("valor_novo"),
                    ip_origem=_ip_origem(),
                    justificativa=detalhes.get("justificativa"),
                )

                # Commit único: alteração da view (ainda pendente na
                # sessão) + log, juntos. Se algo acima já tiver
                # lançado (incluindo a validação de justificativa em
                # DELETE, dentro do service), esta linha nunca é
                # alcançada.
                db.session.commit()

            except Exception:
                # Desfaz TUDO que estava pendente na sessão -- tanto a
                # alteração da view quanto o log parcial, se algum
                # objeto já tinha sido adicionado antes da exceção.
                db.session.rollback()
                raise

            return resposta

        return wrapper

    return decorator


# ======================================================================
# acesso_auditado -- LEITURA sensível: sem step-up, só log
# ======================================================================

def acesso_auditado(recurso, *, operacao):
    """Decorator: registra LogAcesso após a view responder com sucesso.

    Sem step-up -- a sessão autenticada já é suficiente para leitura
    (ver decisão de produto na docstring do módulo). Não é atômico com
    nada da view (leitura não altera dados, não há "outra coisa" para
    commitar junto) -- só grava e commita o próprio log.

    Parâmetros:
        recurso: nome do recurso acessado (`recurso_acessado`).
        operacao: uma das colunas do enum de LogAcesso.operacao
            ("leitura", "escrita", "exclusao-logica", "exportacao").
            OBRIGATÓRIO -- sem default. Antes, o default silencioso
            "leitura" fazia rotas de exportação/escrita ficarem
            registradas como leitura sempre que quem aplicava o
            decorator esquecia de especificar; declarar explicitamente
            aqui obriga a escolha consciente por rota.

    A view pode retornar só a resposta Flask (caso comum), ou
    `(resposta, detalhes)` se quiser especificar `uuid_paciente` ou
    sobrescrever `resultado`/`operacao` dinamicamente.

    Se a view lançar exceção, nada é logado aqui -- a exceção sobe
    normalmente para o error handler padrão da aplicação.
    """
    if operacao not in _OPERACOES_LOG_ACESSO:
        raise ValueError(
            f"acesso_auditado: operacao={operacao!r} invalida. "
            f"Use uma de {_OPERACOES_LOG_ACESSO}."
        )

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            resultado = f(*args, **kwargs)
            resposta, detalhes = _extrair_resposta_e_detalhes(resultado)

            _auditoria.registrar_acesso(
                id_empresa=get_id_empresa_sessao(),
                id_usuario=get_id_usuario_sessao(),
                recurso=detalhes.get("recurso_acessado", recurso),
                operacao=detalhes.get("operacao", operacao),
                ip_origem=_ip_origem(),
                resultado=detalhes.get("resultado", "sucesso"),
                uuid_paciente=detalhes.get("uuid_paciente"),
            )
            db.session.commit()

            return resposta

        return wrapper

    return decorator