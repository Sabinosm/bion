"""
controller.py

Camada HTTP do domínio de auditoria. Expõe, somente para administradores, as
consultas à trilha de auditoria: visão resumida por profissional, histórico
detalhado de um profissional e listagens filtradas dos registros de acesso e
de alteração de dados.

Aqui ficam apenas a leitura e a validação dos parâmetros da requisição e a
montagem da resposta padronizada. As regras de negócio e as consultas
ficam no service.
"""

from datetime import datetime
from typing import Optional

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException
from src.core.session import requer_admin, get_id_empresa_sessao
from .service import AuditoriaService

bp = Blueprint("auditoria", __name__)
_svc = AuditoriaService()

_LIMIT_PADRAO = 10


def _parse_data(valor: Optional[str]) -> Optional[datetime]:
    """Converte uma string ISO 8601 em datetime. Vazio/None vira None; formato inválido levanta ValueError."""
    return datetime.fromisoformat(valor) if valor else None


def _parse_bool(valor: Optional[str]) -> Optional[bool]:
    """Converte 'true'/'false' (sem distinguir maiúsculas) em bool. None vira None; outro valor levanta ValueError."""
    if valor is None:
        return None
    valor = valor.lower()
    if valor not in ("true", "false"):
        raise ValueError(valor)
    return valor == "true"


def _ler_paginacao() -> tuple:
    """Lê page e limit da querystring. page nunca é menor que 1."""
    page = max(request.args.get("page", default=1, type=int), 1)
    limit = request.args.get("limit", default=_LIMIT_PADRAO, type=int)
    return page, limit


def _ler_periodo() -> tuple:
    """Lê data_inicio e data_fim da querystring. Levanta ValueError se algum não for ISO 8601."""
    return _parse_data(request.args.get("data_inicio")), _parse_data(request.args.get("data_fim"))


def _ler_cursor(prefixo: str) -> Optional[dict]:
    """Monta o cursor {"data", "uuid"} de um bloco a partir de cursor_<prefixo>_data/_uuid.

    Sem data, devolve None (começa do registro mais recente).
    """
    data = _parse_data(request.args.get(f"cursor_{prefixo}_data"))
    if not data:
        return None
    return {"data": data, "uuid": request.args.get(f"cursor_{prefixo}_uuid")}


def _log_para_cursor(item_dict: dict, campo_data: str) -> dict:
    """Extrai de um item serializado o par (data, uuid) que o client devolve como cursor."""
    return {"cursor_data": item_dict[campo_data], "cursor_uuid": item_dict["uuid"]}


def _bloco_com_cursor(bloco: dict, campo_data: str) -> dict:
    """Serializa um bloco paginado por cursor (itens, tem_mais, proximo_cursor)."""
    itens = [i.to_dict() for i in bloco["itens"]]
    return {
        "itens": itens,
        "tem_mais": bloco["tem_mais"],
        "proximo_cursor": _log_para_cursor(itens[-1], campo_data) if itens else None,
    }


def _paginado(itens: list, total: int, page: int, limit: int) -> dict:
    """Envolve resultados paginados por offset no formato padrão da API."""
    return {"itens": itens, "paginacao": {"total": total, "page": page, "limit": limit}}


class AuditoriaController():

    @staticmethod
    @bp.get("/profissionais/resumo")
    @requer_admin
    def listar_resumo_profissionais():
        """Lista profissionais paginados com o último log de acesso e de alteração de cada um.

        Query params: nome, funcao_clinica ("medico"/"enfermeiro"), is_admin
        ("true"/"false"), acao, page, limit.
        """
        id_empresa = get_id_empresa_sessao()
        page, limit = _ler_paginacao()

        try:
            is_admin = _parse_bool(request.args.get("is_admin"))
        except ValueError:
            return json_error("is_admin deve ser 'true' ou 'false'.", status=400)

        try:
            itens, total = _svc.listar_resumo_por_profissional(
                id_empresa,
                nome_usuario=request.args.get("nome"),
                funcao_clinica=request.args.get("funcao_clinica"),
                is_admin=is_admin,
                acao=request.args.get("acao"),
                page=page, limit=limit,
            )
        except BionException as e:
            return json_error(e.message, status=e.status_code)

        return json_success(data=_paginado(itens, total, page, limit))

    @staticmethod
    @bp.get("/profissionais/<string:uuid_usuario>/detalhe")
    @requer_admin
    def detalhe_profissional(uuid_usuario: str):
        """Retorna o histórico cronológico de acessos e alterações de um profissional.

        Cada bloco pagina por cursor, de forma independente. Query params:
        acao, operacao_acesso, data_inicio, data_fim, limit,
        cursor_acessos_data/cursor_acessos_uuid e
        cursor_alteracoes_data/cursor_alteracoes_uuid.
        """
        id_empresa = get_id_empresa_sessao()
        limit = request.args.get("limit", default=_LIMIT_PADRAO, type=int)

        try:
            data_inicio, data_fim = _ler_periodo()
            cursor_acessos = _ler_cursor("acessos")
            cursor_alteracoes = _ler_cursor("alteracoes")
        except ValueError:
            return json_error("Datas devem estar em formato ISO 8601", status=400)

        try:
            resultado = _svc.detalhe_profissional(
                id_empresa, uuid_usuario,
                acao=request.args.get("acao"),
                operacao_acesso=request.args.get("operacao_acesso"),
                data_inicio=data_inicio, data_fim=data_fim,
                cursor_acessos=cursor_acessos, cursor_alteracoes=cursor_alteracoes,
                limit=limit,
            )
        except BionException as e:
            return json_error(e.message, status=e.status_code)

        return json_success(data={
            "acessos": _bloco_com_cursor(resultado["acessos"], "data_hora"),
            "alteracoes": _bloco_com_cursor(resultado["alteracoes"], "alterado_em"),
        })

    @staticmethod
    @bp.get("/acessos")
    @requer_admin
    def listar_acessos():
        """Lista registros de acesso filtrados, com paginação.

        Query params: uuid_usuario, nome, operacao, data_inicio, data_fim, page, limit.
        """
        id_empresa = get_id_empresa_sessao()
        page, limit = _ler_paginacao()

        try:
            data_inicio, data_fim = _ler_periodo()
        except ValueError:
            return json_error("data_inicio/data_fim devem estar em formato ISO 8601", status=400)

        try:
            itens, total = _svc.listar_acessos(
                id_empresa,
                uuid_usuario=request.args.get("uuid_usuario"),
                nome_usuario=request.args.get("nome"),
                operacao=request.args.get("operacao"),
                data_inicio=data_inicio, data_fim=data_fim,
                page=page, limit=limit,
            )
        except BionException as e:
            return json_error(e.message, status=e.status_code)

        return json_success(data=_paginado([i.to_dict() for i in itens], total, page, limit))

    @staticmethod
    @bp.get("/alteracoes")
    @requer_admin
    def listar_alteracoes():
        """Lista alterações de dados, com paginação.

        Se 'tabela' e 'uuid_registro' forem informados, faz o drill-down do
        registro (histórico completo, sem paginação e sem os demais filtros).
        Query params: tabela, uuid_registro, uuid_usuario, nome, acao,
        operacao, data_inicio, data_fim, page, limit.
        """
        id_empresa = get_id_empresa_sessao()
        tabela = request.args.get("tabela")
        uuid_registro = request.args.get("uuid_registro")
        page, limit = _ler_paginacao()

        try:
            data_inicio, data_fim = _ler_periodo()
        except ValueError:
            return json_error("data_inicio/data_fim devem estar em formato ISO 8601", status=400)

        try:
            resultado = _svc.listar_alteracoes(
                id_empresa,
                tabela_origem=tabela, uuid_registro=uuid_registro,
                uuid_usuario=request.args.get("uuid_usuario"),
                nome_usuario=request.args.get("nome"),
                acao=request.args.get("acao"),
                operacao=request.args.get("operacao"),
                data_inicio=data_inicio, data_fim=data_fim,
                page=page, limit=limit,
            )
        except BionException as e:
            return json_error(e.message, status=e.status_code)

        if tabela and uuid_registro:
            return json_success(data={"itens": [i.to_dict() for i in resultado]})

        itens, total = resultado
        return json_success(data=_paginado([i.to_dict() for i in itens], total, page, limit))