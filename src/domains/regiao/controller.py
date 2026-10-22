"""
controller.py

Rotas JSON do domínio Região Geográfica (municípios, estados e demais unidades
territoriais). Permite listar as regiões (paginado, de 15 em 15), consultar
uma pelo UUID, pelo código IBGE ou pelo CEP. Na consulta por código IBGE e por CEP, uma região que ainda
não existe no banco pode ser confirmada nas APIs públicas e cadastrada
automaticamente. Todas as rotas exigem apenas login.
"""

from flask import Blueprint, request

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException, DadosInvalidosError
from src.core.session import requer_login
from src.core.validacoes import validar_e_devolver_cep
from .service import RegiaoService, codigo_municipio_valido
from .repository import PER_PAGE_PADRAO
from .cep_service import CepService

bp = Blueprint("regiao", __name__)
_svc = RegiaoService()
_cep_svc = CepService()


class RegiaoController():

    @staticmethod
    @bp.get("/")
    @requer_login
    def lista():
        """Lista as regiões em ordem alfabética, paginadas, todas ou só as de um tipo.

        Query: `tipo` (opcional), código do tipo de jurisdição, ex.: `municipio`;
        `page` (padrão 1) e `limit` (padrão 15, máximo 50).
        A resposta traz `itens` e `paginacao` (`total`, `page`, `limit`).
        """
        page = request.args.get("page", default=1, type=int)
        limit = request.args.get("limit", default=PER_PAGE_PADRAO, type=int)

        resultado = _svc.listar_paginado(request.args.get("tipo"), page, limit)
        return json_success(data={
            "itens": [r.to_dict() for r in resultado["itens"]],
            "paginacao": {
                "total": resultado["total"],
                "page": resultado["page"],
                "limit": resultado["limit"],
            },
        })

    @staticmethod
    @bp.get("/uuid/<uuid>")
    @requer_login
    def detalhe(uuid):
        """Detalhes de uma região geográfica pelo UUID."""
        try:
            r = _svc.buscar_por_uuid(uuid)
            return json_success(data=r.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.get("/codigo/<codigo_ibge>")
    @requer_login
    def detalhe_por_codigo(codigo_ibge: str):
        """Detalhes de uma região pelo código IBGE do município.

        O código precisa ter 7 dígitos; fora do formato é recusado como dados
        inválidos. Se o código não existir no banco, tenta confirmá-lo na API
        do IBGE e cadastrar a região. Só responde 404 se o código também não
        existir no IBGE (ou se a consulta externa falhar).
        """
        try:
            if not codigo_municipio_valido(codigo_ibge):
                raise DadosInvalidosError(f"Código IBGE inválido: {codigo_ibge}")

            r = _svc.buscar_ou_criar_por_codigo_ibge(codigo_ibge)
            if not r:
                return json_error(f"Região geográfica não encontrada: {codigo_ibge}", 404)
            return json_success(data=r.to_dict())
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.get("/cep/<cep>")
    @requer_login
    def detalhe_por_cep(cep: str):
        """Região geográfica (município) correspondente ao CEP informado.

        Resolve o CEP em código IBGE e devolve a região, cadastrando-a se
        necessário. A resposta é o objeto da região direto, sem o envelope
        `data`. O CEP precisa ter 8 dígitos (com ou sem hífen); fora do formato
        é recusado como dados inválidos. Responde 404 se o CEP não existir ou
        não tiver região resolvível.
        """
        try:
            if validar_e_devolver_cep(cep) is None:
                raise DadosInvalidosError(f"CEP inválido: {cep}")

            regiao = _cep_svc.regiao_por_cep(cep)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

        if regiao:
            return regiao.to_dict()
        return json_error(f"Região geográfica não encontrada para o CEP: {cep}", 404)