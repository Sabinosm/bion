"""
cep_service.py

Serviço utilitário de consulta de CEP. Resolve bairro, logradouro, código IBGE
e coordenadas (latitude e longitude) a partir de um CEP, para uso em agregações
territoriais (ex.: avaliação de endemias por bairro ou por município) sem
reter nem expor o CEP completo do paciente ou da empresa em relatórios. O CEP
completo continua guardado onde já está (Empresa, Paciente); este serviço só
devolve o que for pedido dele.

Fonte primária: BrasilAPI (v2), que devolve bairro, código IBGE do município
(em `ibge.city`) e coordenadas no mesmo payload, agregando vários provedores
por baixo dos panos. Fallback: ViaCEP, usado se a BrasilAPI falhar ou estiver
fora do ar. O ViaCEP não devolve coordenadas, então, quando o fallback é usado,
o resultado traz bairro e código IBGE mas latitude e longitude vêm como None.

Os resultados ficam em cache em memória por CEP, para não consultar a API de
novo (muitos pacientes e empresas compartilham o mesmo CEP). Guarda-se o
endereço encontrado e o "não encontrado" DEFINITIVO, quando as duas fontes
confirmam que o CEP não existe. Falhas passageiras (rede, tempo esgotado,
resposta inesperada) NÃO são guardadas, para o CEP ser consultado de novo. O
cache é por processo: com vários workers, cada um mantém o seu.

Privacidade: mesmo sendo uma generalização do CEP, "bairro + condição de
saúde" ainda pode ser dado pessoal sensível, dependendo do volume de casos no
bairro (ver k-anonimato). Este serviço só resolve CEP em
bairro/IBGE/coordenadas; como agregar e expor isso em relatórios (ex.: limiar
mínimo de casos antes de exibir) é responsabilidade de quem o consome.
"""

from typing import Optional

import requests

from src.models.corp.regiao_geografica import RegiaoGeografica
from src.core.validacoes import validar_e_devolver_cep

BRASILAPI_CEP_URL = "https://brasilapi.com.br/api/cep/v2/{cep}"
VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
CEP_TIMEOUT_SEGUNDOS = 5

# CEP limpo -> endereço já resolvido (dict) ou None, este último significando
# "não existe" confirmado pelas duas fontes. Falhas passageiras não entram aqui.
_cache_endereco_por_cep: dict = {}

# Resposta de UMA fonte que confirma que o CEP não existe. Diferente de falha
# (rede, tempo esgotado, resposta inesperada), que uma fonte devolve como None.
_NAO_ENCONTRADO = object()

_SITUACAO_OK = "ok"
_SITUACAO_NAO_ENCONTRADO = "nao_encontrado"
_SITUACAO_FALHA = "falha"


def _obter_json(url: str) -> tuple:
    """GET que devolve (situacao, dados).

    `situacao` é "ok" (status 200 com JSON válido, que vem em `dados`),
    "nao_encontrado" (status 404: a fonte confirma que o CEP não existe) ou
    "falha" (erro de rede, tempo esgotado, outro status ou corpo que não é
    JSON). Fora do caso "ok", `dados` é None.
    """
    try:
        resposta = requests.get(url, timeout=CEP_TIMEOUT_SEGUNDOS)
    except requests.RequestException:
        return _SITUACAO_FALHA, None

    if resposta.status_code == 404:
        return _SITUACAO_NAO_ENCONTRADO, None
    if resposta.status_code != 200:
        return _SITUACAO_FALHA, None

    try:
        return _SITUACAO_OK, resposta.json()
    except ValueError:
        return _SITUACAO_FALHA, None


class CepService:

    # ------------------------------------------------------------------
    # Região
    # ------------------------------------------------------------------

    def regiao_por_cep(self, cep: str) -> Optional[RegiaoGeografica]:
        """Região (município) do CEP, cadastrada automaticamente se ainda não existir.

        Returns:
            A região, ou None se o CEP for inválido, não existir ou não tiver
            código IBGE resolvível.
        """
        from src.domains.regiao.service import RegiaoService

        codigo_ibge = self.buscar_codigo_ibge_por_cep(cep)
        if not codigo_ibge:
            return None

        return RegiaoService().buscar_ou_criar_por_codigo_ibge(codigo_ibge)

    # ------------------------------------------------------------------
    # Endereço
    # ------------------------------------------------------------------

    def buscar_endereco_por_cep(self, cep: str) -> Optional[dict]:
        """Consulta o CEP (BrasilAPI primeiro, ViaCEP como fallback).

        O endereço encontrado fica em cache em memória por CEP. O "não
        encontrado" só entra no cache quando as DUAS fontes confirmam que o
        CEP não existe; se alguma falhou (rede, tempo esgotado, resposta
        inesperada) e nenhuma achou o CEP, o resultado é None mas nada é
        guardado, e a próxima chamada consulta de novo. Cada chamada devolve
        uma cópia, então alterar o resultado não afeta o cache.

        Returns:
            {"bairro", "logradouro", "codigo_ibge", "latitude", "longitude"},
            cada campo podendo ser None, ou None se o CEP tiver formato
            inválido, não existir ou as fontes falharem.
        """
        cep_limpo = validar_e_devolver_cep(cep)
        if cep_limpo is None:
            return None

        if cep_limpo not in _cache_endereco_por_cep:
            brasilapi = self._consultar_brasilapi(cep_limpo)
            if isinstance(brasilapi, dict):
                _cache_endereco_por_cep[cep_limpo] = brasilapi
            else:
                viacep = self._consultar_viacep(cep_limpo)
                if isinstance(viacep, dict):
                    _cache_endereco_por_cep[cep_limpo] = viacep
                elif brasilapi is _NAO_ENCONTRADO and viacep is _NAO_ENCONTRADO:
                    _cache_endereco_por_cep[cep_limpo] = None
                else:
                    return None

        resultado = _cache_endereco_por_cep[cep_limpo]
        return dict(resultado) if resultado is not None else None

    def buscar_bairro_por_cep(self, cep: str) -> Optional[str]:
        """Atalho para quem só precisa do bairro."""
        endereco = self.buscar_endereco_por_cep(cep)
        return endereco["bairro"] if endereco else None

    def buscar_logradouro_por_cep(self, cep: str) -> Optional[str]:
        """Atalho para quem só precisa da rua.

        None em CEP "geral" (cidade pequena com CEP único): nesses casos a API
        não tem rua.
        """
        endereco = self.buscar_endereco_por_cep(cep)
        return endereco.get("logradouro") if endereco else None

    def buscar_codigo_ibge_por_cep(self, cep: str) -> Optional[str]:
        """Atalho para quem só precisa do código IBGE do município."""
        endereco = self.buscar_endereco_por_cep(cep)
        return endereco["codigo_ibge"] if endereco else None

    def buscar_coordenadas_por_cep(self, cep: str) -> Optional[dict]:
        """Atalho para quem só precisa das coordenadas do CEP.

        Returns:
            {"latitude": float, "longitude": float}, ou None se o CEP for
            inválido ou inexistente, ou se as coordenadas não estiverem
            disponíveis (ex.: resultado vindo do fallback ViaCEP, que não as
            devolve).
        """
        endereco = self.buscar_endereco_por_cep(cep)
        if not endereco or endereco["latitude"] is None or endereco["longitude"] is None:
            return None
        return {"latitude": endereco["latitude"], "longitude": endereco["longitude"]}

    # ------------------------------------------------------------------
    # Fontes externas
    # ------------------------------------------------------------------

    def _consultar_brasilapi(self, cep_limpo: str):
        """Fonte primária. Devolve bairro, logradouro, código IBGE e coordenadas.

        O código IBGE vem de `ibge.city` e as coordenadas de
        `location.coordinates`, quando presentes: nem todo CEP tem coordenadas
        na BrasilAPI.

        Returns:
            O endereço (dict) no formato de `buscar_endereco_por_cep`;
            `_NAO_ENCONTRADO` se a fonte confirma que o CEP não existe; ou
            None se a consulta falhar ou o payload for inesperado.
        """
        situacao, dados = _obter_json(BRASILAPI_CEP_URL.format(cep=cep_limpo))
        if situacao == _SITUACAO_NAO_ENCONTRADO:
            return _NAO_ENCONTRADO
        if situacao != _SITUACAO_OK:
            return None

        try:
            codigo_ibge = None
            ibge = dados.get("ibge")
            if isinstance(ibge, dict):
                codigo_ibge_bruto = ibge.get("city")
                codigo_ibge = str(codigo_ibge_bruto) if codigo_ibge_bruto else None

            latitude, longitude = self._extrair_coordenadas_brasilapi(dados)

            return {
                "bairro": dados.get("neighborhood") or None,
                "logradouro": dados.get("street") or None,
                "codigo_ibge": codigo_ibge,
                "latitude": latitude,
                "longitude": longitude,
            }
        except (TypeError, AttributeError):
            return None

    @staticmethod
    def _extrair_coordenadas_brasilapi(dados: dict) -> tuple:
        """(latitude, longitude) do payload da BrasilAPI, cada um None se ausente ou inválido."""
        location = dados.get("location")
        if not isinstance(location, dict):
            return None, None

        coordinates = location.get("coordinates")
        if not isinstance(coordinates, dict):
            return None, None

        try:
            lat_bruta = coordinates.get("latitude")
            lon_bruta = coordinates.get("longitude")
            latitude = float(lat_bruta) if lat_bruta not in (None, "") else None
            longitude = float(lon_bruta) if lon_bruta not in (None, "") else None
            return latitude, longitude
        except (ValueError, TypeError):
            return None, None

    def _consultar_viacep(self, cep_limpo: str):
        """Fallback, usado quando a BrasilAPI falha ou não encontra o CEP.

        Não devolve coordenadas: o ViaCEP não as traz no payload.

        Returns:
            O endereço (dict) no formato de `buscar_endereco_por_cep`
            (latitude e longitude sempre None); `_NAO_ENCONTRADO` se a fonte
            confirma que o CEP não existe; ou None se a consulta falhar ou o
            payload for inesperado.
        """
        situacao, dados = _obter_json(VIACEP_URL.format(cep=cep_limpo))
        if situacao == _SITUACAO_NAO_ENCONTRADO:
            return _NAO_ENCONTRADO
        if situacao != _SITUACAO_OK:
            return None

        try:
            # O ViaCEP responde 200 com {"erro": true} para CEP inexistente,
            # em vez de usar o status HTTP 404.
            if dados.get("erro"):
                return _NAO_ENCONTRADO

            return {
                "bairro": dados.get("bairro") or None,
                "logradouro": dados.get("logradouro") or None,
                "codigo_ibge": dados.get("ibge") or None,
                "latitude": None,
                "longitude": None,
            }
        except (TypeError, AttributeError):
            return None