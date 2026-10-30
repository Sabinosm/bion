"""
acaoSensivel.py

Decorators de auditoria para views Flask que lidam com dados sensíveis.

Um decorator cobre ações de escrita e exclusão: exige reconfirmação recente de
identidade (step-up) e grava o log de alteração na mesma transação da ação,
com um único commit no final. O outro cobre leituras sensíveis: grava o log de
acesso depois que a view responde com sucesso, sem exigir step-up.

Em ambos os casos a view devolve a resposta Flask junto de um dicionário de
detalhes que alimenta o log, e o commit é responsabilidade do decorator, nunca
da view.
"""

import os
from functools import wraps

from flask import request

from src.models import db
from src.domains.auth.step_up import StepUp
from src.domains.auditoria.service import AuditoriaService
from src.core.session import get_id_usuario_sessao, get_id_empresa_sessao

_auditoria = AuditoriaService()
_OPERACOES_LOG_ACESSO = ("leitura", "escrita", "exclusao-logica", "exportacao")

# Sinal devolvido pela view em detalhes["operacao"] quando nada foi alterado
# (ex.: erro de validação). Não é uma operação auditável em nenhum dos logs.
_OPERACAO_NOOP = "NOOP"


def ip_cliente():
    """IP do cliente sem confiar cegamente no X-Forwarded-For.

    TRUSTED_PROXY_HOPS = quantos proxies SEUS ficam na frente do Flask
    (0 = nenhum: usa o remote_addr; 1 = nginx/ALB: pega o último IP da
    cadeia, que foi o proxy que anexou). O cliente pode forjar o começo
    da cadeia, mas não o trecho que o seu proxy anexa.

    É o critério único de IP do sistema: os logs de auditoria e o
    consentimento digital usam esta mesma função. Alternativa equivalente:
    werkzeug ProxyFix com x_for=<hops> e usar só request.remote_addr.
    """
    hops = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))
    xff = request.headers.get("X-Forwarded-For", "")
    if hops > 0 and xff:
        partes = [p.strip() for p in xff.split(",") if p.strip()]
        if len(partes) >= hops:
            return partes[-hops]
    return request.remote_addr


def _ip_origem():
    """IP de origem gravado nos logs (ver ip_cliente)."""
    return ip_cliente()


def _extrair_resposta_e_detalhes(resultado):
    """Separa o retorno da view em (resposta_flask, detalhes_dict).

    Se a view não devolver uma tupla (resposta, dict), os detalhes vêm vazios.
    """
    if isinstance(resultado, tuple) and len(resultado) == 2 and isinstance(resultado[1], dict):
        return resultado
    return resultado, {}


def _status_da_resposta(resposta):
    """Extrai o status HTTP da resposta da view.

    Aceita Response e tupla (Response, status), que é o formato que algumas
    implementações de json_error devolvem.
    """
    if isinstance(resposta, tuple):
        if len(resposta) >= 2 and isinstance(resposta[1], int):
            return resposta[1]
        resposta = resposta[0]
    return getattr(resposta, "status_code", 200)


def acao_sensivel(acao: str, *, tabela: str):
    """Decorator para escrita/exclusão: exige step-up recente e audita de forma atômica.

    A view decorada NÃO deve executar db.session.commit(); deve retornar
    (resposta, detalhes), com 'id_registro' e 'uuid_registro' obrigatórios.
    Chaves opcionais de `detalhes`: tabela_origem, operacao (padrão "UPDATE"),
    campo_alterado, valor_anterior, valor_novo e justificativa (obrigatória
    quando operacao == "DELETE").

    Qualquer exceção (da view ou do log) desfaz a transação inteira. Se a view
    devolver uma resposta de erro (status >= 400) ou operacao == "NOOP" sem
    lançar exceção, a transação também é desfeita e nenhum log de alteração é
    gravado: a ação não aconteceu, então não há o que auditar nem o que
    commitar.

    Args:
        acao: nome da ação auditada (ex.: "editar_paciente"); também é a ação
            vinculada ao token de step-up.
        tabela: tabela de origem padrão do log de alteração.
    """
    if not tabela:
        raise ValueError(f"acao_sensivel({acao!r}) exige o parâmetro 'tabela'")

    confirmar_identidade = StepUp.requer_confirmacao_recente(acao)

    def decorator(f):
        @wraps(f)
        @confirmar_identidade
        def wrapper(*args, **kwargs):
            try:
                resposta, detalhes = _extrair_resposta_e_detalhes(f(*args, **kwargs))

                if detalhes.get("operacao") == _OPERACAO_NOOP or _status_da_resposta(resposta) >= 400:
                    db.session.rollback()
                    return resposta

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
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            return resposta
        return wrapper
    return decorator


def acesso_auditado(recurso: str, *, operacao: str):
    """Decorator para leitura sensível: registra o log de acesso após a view ter sucesso.

    Não exige step-up. A view pode devolver (resposta, detalhes) para
    sobrescrever recurso_acessado, operacao, resultado e informar uuid_paciente.

    Se detalhes["operacao"] == "NOOP", nada é registrado (mesmo sinal que
    acao_sensivel entende). Qualquer outra operacao vinda dos detalhes precisa
    estar em _OPERACOES_LOG_ACESSO, senão levanta ValueError com mensagem clara
    em vez de estourar no banco (coluna ENUM).

    Args:
        recurso: recurso acessado, usado como padrão no log.
        operacao: obrigatória, uma de _OPERACOES_LOG_ACESSO, para evitar
            registrar toda leitura como se fosse a mesma categoria.
    """
    if operacao not in _OPERACOES_LOG_ACESSO:
        raise ValueError(
            f"acesso_auditado: operacao={operacao!r} invalida. Use uma de {_OPERACOES_LOG_ACESSO}."
        )

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            resposta, detalhes = _extrair_resposta_e_detalhes(f(*args, **kwargs))

            if detalhes.get("operacao") == _OPERACAO_NOOP:
                db.session.rollback()
                return resposta

            try:
                operacao_log = detalhes.get("operacao", operacao)
                if operacao_log not in _OPERACOES_LOG_ACESSO:
                    raise ValueError(
                        f"acesso_auditado({recurso!r}): operacao={operacao_log!r} invalida "
                        f"vinda dos detalhes da view. Use uma de {_OPERACOES_LOG_ACESSO}. "
                        f"(Se a view faz escrita com step-up, use @acao_sensivel.)"
                    )

                _auditoria.registrar_acesso(
                    id_empresa=get_id_empresa_sessao(),
                    id_usuario=get_id_usuario_sessao(),
                    recurso=detalhes.get("recurso_acessado", recurso),
                    operacao=operacao_log,
                    ip_origem=_ip_origem(),
                    resultado=detalhes.get("resultado", "sucesso"),
                    uuid_paciente=detalhes.get("uuid_paciente"),
                )
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            return resposta
        return wrapper
    return decorator