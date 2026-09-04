"""Rotas JSON do dominio Auditoria (somente leitura para administradores).

Todas as rotas exigem id_empresa vindo da sessao autenticada (nunca do
query string) -- fecha o bug de permissao entre tenants.

Nenhuma rota aceita ou devolve id_usuario (PK interna). Profissionais
sao sempre referenciados por uuid_usuario.

Respostas usam json_success/json_error de src.core.responses, que NAO
tem parametro `meta` -- por isso toda info de paginacao vai dentro de
`data`, no formato {"itens": [...], "paginacao": {...}}, em vez de um
campo separado no payload.

Paginacao:
- /profissionais/resumo, /acessos, /alteracoes: offset/limit
  convencional via `page` + `limit` (limit maximo travado no backend,
  ver LIMIT_MAXIMO em repository.py -- hoje 50).
- /profissionais/<uuid>/detalhe: cursor por data (`cursor_data` +
  `cursor_uuid`), ja que aqui a navegacao e cronologica e sofreria com
  offset em um log que recebe eventos em tempo real (ver service.py).
"""

from datetime import datetime

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_papel, get_id_empresa_sessao
from .service import AuditoriaService

bp = Blueprint("auditoria", __name__)
_svc = AuditoriaService()


def _parse_data(valor: str):
    if not valor:
        return None
    return datetime.fromisoformat(valor)


def _log_para_cursor(item_dict: dict, campo_data: str) -> dict:
    """Extrai {data, uuid} de um item ja serializado, para o front
    devolver como cursor na proxima chamada -- evita o client ter que
    montar isso na mao a partir de campos separados."""
    return {"cursor_data": item_dict[campo_data], "cursor_uuid": item_dict["uuid"]}


def _paginado(itens: list, total: int, page: int, limit: int):
    """Formato padrao de resposta paginada (offset/limit), usado nas
    3 rotas que paginam assim. Fica dentro de `data` porque
    json_success nao aceita um campo `meta` separado."""
    return {
        "itens": itens,
        "paginacao": {"total": total, "page": page, "limit": limit},
    }


class AuditoriaController():

    @staticmethod
    @bp.get("/profissionais/resumo")
    @requer_papel("admin")
    def listar_resumo_profissionais():
        """Tela principal: profissionais em ordem alfabetica, paginados,
        cada um com seu ultimo acesso e ultima alteracao.

        Query params: nome, tipo_usuario, acao, page (default 1), limit
        (default 10, maximo 50).
        """
        id_empresa = get_id_empresa_sessao()
        nome = request.args.get("nome")
        tipo_usuario = request.args.get("tipo_usuario")
        acao = request.args.get("acao")
        page = request.args.get("page", default=1, type=int)
        limit = request.args.get("limit", default=10, type=int)

        try:
            itens, total = _svc.listar_resumo_por_profissional(
                id_empresa, nome_usuario=nome, tipo_usuario=tipo_usuario, acao=acao,
                page=page, limit=limit,
            )
        except BionException as e:
            return json_error(e.message, status=e.status_code)

        return json_success(data=_paginado(itens, total, page, limit))

    @staticmethod
    @bp.get("/profissionais/<string:uuid_usuario>/detalhe")
    @requer_papel("admin")
    def detalhe_profissional(uuid_usuario: str):
        """Historico completo (acesso + alteracao) de UM profissional,
        identificado por uuid. Paginado por cursor de data em cada
        bloco, independente.

        Query params comuns: acao (traduzido tambem para alteracao, ver
        service), data_inicio, data_fim, limit (default 10, maximo 50).
        Query params de acesso: operacao_acesso.
        Cursores (para "carregar mais", devolvidos pelo item anterior):
        cursor_acessos_data, cursor_acessos_uuid,
        cursor_alteracoes_data, cursor_alteracoes_uuid.
        """
        id_empresa = get_id_empresa_sessao()
        acao = request.args.get("acao")
        operacao_acesso = request.args.get("operacao_acesso")
        limit = request.args.get("limit", default=10, type=int)

        try:
            data_inicio = _parse_data(request.args.get("data_inicio"))
            data_fim = _parse_data(request.args.get("data_fim"))
            cursor_acessos_data = _parse_data(request.args.get("cursor_acessos_data"))
            cursor_alteracoes_data = _parse_data(request.args.get("cursor_alteracoes_data"))
        except ValueError:
            return json_error("Datas devem estar em formato ISO 8601", status=400)

        cursor_acessos = None
        if cursor_acessos_data:
            cursor_acessos = {"data": cursor_acessos_data,
                               "uuid": request.args.get("cursor_acessos_uuid")}

        cursor_alteracoes = None
        if cursor_alteracoes_data:
            cursor_alteracoes = {"data": cursor_alteracoes_data,
                                  "uuid": request.args.get("cursor_alteracoes_uuid")}

        try:
            resultado = _svc.detalhe_profissional(
                id_empresa, uuid_usuario, acao=acao, operacao_acesso=operacao_acesso,
                data_inicio=data_inicio, data_fim=data_fim,
                cursor_acessos=cursor_acessos, cursor_alteracoes=cursor_alteracoes,
                limit=limit,
            )
        except BionException as e:
            return json_error(e.message, status=e.status_code)

        acessos_dict = [i.to_dict() for i in resultado["acessos"]["itens"]]
        alteracoes_dict = [i.to_dict() for i in resultado["alteracoes"]["itens"]]

        return json_success(data={
            "acessos": {
                "itens": acessos_dict,
                "tem_mais": resultado["acessos"]["tem_mais"],
                "proximo_cursor": (
                    _log_para_cursor(acessos_dict[-1], "data_hora") if acessos_dict else None
                ),
            },
            "alteracoes": {
                "itens": alteracoes_dict,
                "tem_mais": resultado["alteracoes"]["tem_mais"],
                "proximo_cursor": (
                    _log_para_cursor(alteracoes_dict[-1], "alterado_em") if alteracoes_dict else None
                ),
            },
        })

    @staticmethod
    @bp.get("/acessos")
    @requer_papel("admin")
    def listar_acessos():
        """Filtros: uuid_usuario, nome, operacao, data_inicio, data_fim,
        page, limit (default 10, maximo 50)."""
        id_empresa = get_id_empresa_sessao()
        uuid_usuario = request.args.get("uuid_usuario")
        nome = request.args.get("nome")
        operacao = request.args.get("operacao")
        page = request.args.get("page", default=1, type=int)
        limit = request.args.get("limit", default=10, type=int)

        try:
            data_inicio = _parse_data(request.args.get("data_inicio"))
            data_fim = _parse_data(request.args.get("data_fim"))
        except ValueError:
            return json_error("data_inicio/data_fim devem estar em formato ISO 8601", status=400)

        try:
            itens, total = _svc.listar_acessos(
                id_empresa, uuid_usuario=uuid_usuario, nome_usuario=nome, operacao=operacao,
                data_inicio=data_inicio, data_fim=data_fim, page=page, limit=limit,
            )
        except BionException as e:
            return json_error(e.message, status=e.status_code)

        return json_success(data=_paginado([i.to_dict() for i in itens], total, page, limit))

    @staticmethod
    @bp.get("/alteracoes")
    @requer_papel("admin")
    def listar_alteracoes():
        """Filtros: tabela+uuid_registro (drill-down, sem paginacao),
        uuid_usuario, nome, acao (texto livre, ex: "editar_paciente"),
        operacao (categoria de negocio: leitura/escrita/exclusao-logica/
        exportacao -- traduzida internamente para INSERT/UPDATE/DELETE,
        ver service), data_inicio, data_fim, page, limit (default 10,
        maximo 50)."""
        id_empresa = get_id_empresa_sessao()
        tabela = request.args.get("tabela")
        uuid_registro = request.args.get("uuid_registro")
        uuid_usuario = request.args.get("uuid_usuario")
        nome = request.args.get("nome")
        acao = request.args.get("acao")
        operacao = request.args.get("operacao")
        page = request.args.get("page", default=1, type=int)
        limit = request.args.get("limit", default=10, type=int)

        try:
            data_inicio = _parse_data(request.args.get("data_inicio"))
            data_fim = _parse_data(request.args.get("data_fim"))
        except ValueError:
            return json_error("data_inicio/data_fim devem estar em formato ISO 8601", status=400)

        try:
            resultado = _svc.listar_alteracoes(
                id_empresa, tabela_origem=tabela, uuid_registro=uuid_registro,
                uuid_usuario=uuid_usuario, nome_usuario=nome, acao=acao, operacao=operacao,
                data_inicio=data_inicio, data_fim=data_fim, page=page, limit=limit,
            )
        except BionException as e:
            return json_error(e.message, status=e.status_code)

        if tabela and uuid_registro:
            # drill-down: lista pura, sem paginacao (ver service)
            return json_success(data={"itens": [i.to_dict() for i in resultado]})

        itens, total = resultado
        return json_success(data=_paginado([i.to_dict() for i in itens], total, page, limit))