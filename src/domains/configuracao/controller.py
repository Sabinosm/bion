"""
controller.py

Rotas JSON do domínio Configuração, as preferências de cada usuário. Cobre a
leitura e a atualização das configurações de aparência e idioma e o
gerenciamento dos protocolos clínicos do usuário: listar, habilitar, desabilitar
e definir ou remover o padrão pessoal, além de resolver qual protocolo a
consulta carrega por padrão.

Os protocolos são identificados pelo UUID do catálogo (o mesmo que a página de
catálogo já usa); o id numérico não sai do backend. O prefixo real do
blueprint é /v1/api/configuracoes (ver main.py). As rotas de protocolo exigem
papel clínico (médico ou enfermeiro); as de configuração só exigem login.
"""

from flask import Blueprint, request, g

from src.core.responses import json_success, json_error
from src.core.exceptions import BionException, DadosInvalidosError
from src.core.session import requer_login, requer_papel_clinico
from .service import ConfiguracaoService

bp = Blueprint("configuracao", __name__)
_svc = ConfiguracaoService()


def _corpo_json() -> dict:
    """Corpo da requisição como objeto JSON.

    Corpo ausente ou vazio vira {}. Qualquer outro formato (lista, texto,
    número) levanta DadosInvalidosError, em vez de estourar mais adiante.
    """
    dados = request.get_json(silent=True)
    if dados is None:
        return {}
    if not isinstance(dados, dict):
        raise DadosInvalidosError("Corpo inválido. Envie um objeto JSON.")
    return dados


class ConfiguracaoController():

    # ------------------------------------------------------------------
    # Configurações do usuário
    # ------------------------------------------------------------------

    @staticmethod
    @bp.get("/")
    @requer_login
    def minha_configuracao():
        """Configurações do usuário logado, criadas com os padrões no primeiro acesso."""
        cfg = _svc.obter_ou_criar(g.id_usuario)
        return json_success(data={"configuracoes": cfg.to_dict()})

    @staticmethod
    @bp.put("/")
    @requer_login
    def atualizar():
        """Atualiza as configurações por merge parcial por seção.

        Corpo (JSON): {"configuracoes": {"design": {...}, "preferencias": {...}}},
        com qualquer subconjunto dos campos; o que for enviado é validado.
        """
        try:
            dados = _corpo_json()
            cfg = _svc.atualizar(g.id_usuario, dados.get("configuracoes", {}))
            return json_success(data={"configuracoes": cfg.to_dict()}, message="Configurações atualizadas.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    # ------------------------------------------------------------------
    # Protocolos do usuário (papel clínico)
    # ------------------------------------------------------------------

    @staticmethod
    @bp.get("/protocolos/default")
    @requer_papel_clinico("medico", "enfermeiro")
    def default_efetivo():
        """Protocolo que a consulta carrega por padrão para um escopo.

        Query: `escopo` = triagem | consulta | ambos. Cadeia de decisão:
        padrão pessoal, depois institucional, depois o primeiro liberado.
        A resposta traz o protocolo e a `origem` da escolha.
        """
        try:
            catalogo, origem = _svc.resolver_default(g.id_usuario, request.args.get("escopo"))
            return json_success(data={
                "protocolo": {
                    "uuid": catalogo.uuid,
                    "nome_protocolo": catalogo.nome_protocolo,
                    "sigla": catalogo.sigla,
                    "escopo_uso": catalogo.escopo_uso,
                },
                "origem": origem,
            })
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.get("/protocolos")
    @requer_papel_clinico("medico", "enfermeiro")
    def listar_protocolos():
        """Lista as preferências de protocolo do usuário, só dos protocolos que a empresa mantém liberados.

        Cada item traz uuid, sigla, em_uso e escopo_default; é o que a página
        de catálogo cruza com os cards para pintar a estrela.
        """
        protocolos = _svc.listar_protocolos(g.id_usuario)
        return json_success(data=[p.to_dict() for p in protocolos])

    @staticmethod
    @bp.put("/protocolos/<uuid_protocolo>/habilitar")
    @requer_papel_clinico("medico", "enfermeiro")
    def habilitar_protocolo(uuid_protocolo):
        """Habilita um protocolo para o usuário; só vale para os liberados pela instituição."""
        try:
            protocolo = _svc.habilitar_protocolo(g.id_usuario, uuid_protocolo)
            return json_success(data=protocolo.to_dict(), message="Protocolo habilitado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.put("/protocolos/<uuid_protocolo>/desabilitar")
    @requer_papel_clinico("medico", "enfermeiro")
    def desabilitar_protocolo(uuid_protocolo):
        """Desabilita um protocolo; recusado se for obrigatório ou o padrão da instituição."""
        try:
            protocolo = _svc.desabilitar_protocolo(g.id_usuario, uuid_protocolo)
            return json_success(data=protocolo.to_dict(), message="Protocolo desabilitado.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.put("/protocolos/<uuid_protocolo>/default")
    @requer_papel_clinico("medico", "enfermeiro")
    def definir_default(uuid_protocolo):
        """Define o protocolo como padrão pessoal de um escopo.

        Corpo (JSON): {"escopo": "triagem" | "consulta" | "ambos"}.
        """
        try:
            dados = _corpo_json()
            protocolo = _svc.definir_default_pessoal(
                g.id_usuario, uuid_protocolo, dados.get("escopo")
            )
            return json_success(data=protocolo.to_dict(), message="Protocolo definido como padrão.")
        except BionException as ex:
            return json_error(ex.message, ex.status_code)

    @staticmethod
    @bp.delete("/protocolos/<uuid_protocolo>/default")
    @requer_papel_clinico("medico", "enfermeiro")
    def remover_default(uuid_protocolo):
        """Remove o padrão pessoal do protocolo, sem desabilitá-lo; volta a valer o padrão da instituição."""
        try:
            protocolo = _svc.remover_default_pessoal(g.id_usuario, uuid_protocolo)
            return json_success(
                data=protocolo.to_dict(),
                message="Padrão pessoal removido; vale o padrão da instituição.",
            )
        except BionException as ex:
            return json_error(ex.message, ex.status_code)
