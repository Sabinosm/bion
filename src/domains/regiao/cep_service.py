"""
Serviço utilitário de consulta de CEP.

Objetivo: resolver `bairro`, `codigo_ibge` e coordenadas (latitude/
longitude) a partir de um CEP, para uso em agregações territoriais
(ex: avaliação de endemias por bairro ou por município) sem precisar
reter/expor o CEP completo do paciente/empresa em relatórios -- o CEP
completo continua guardado onde já está (Empresa, Paciente), este
serviço só devolve o que for pedido dele.

ESTRATÉGIA DE FONTE: BrasilAPI (v2) como fonte primária -- devolve
bairro, código IBGE do município (em `ibge.city`) E coordenadas
(latitude/longitude) no mesmo payload, agregando múltiplos provedores
por baixo dos panos. ViaCEP como fallback caso a BrasilAPI falhe ou
esteja fora do ar. Diferença de payload entre as duas fontes: o
ViaCEP não devolve coordenadas -- por isso, quando o fallback é
usado, o resultado tem bairro e codigo_ibge, mas latitude/longitude
vêm como None.

NOTA IMPORTANTE SOBRE PRIVACIDADE: mesmo bairro/município sendo uma
generalização do CEP, "bairro + condição de saúde" ainda pode ser dado
pessoal sensível dependendo do volume de casos naquele bairro (ver
k-anonimato). Este serviço só resolve CEP -> bairro/ibge/coordenadas;
a decisão de como agregar/expor isso em relatórios (ex: limiar mínimo
de casos antes de exibir) é responsabilidade de quem consome este
serviço, não deste módulo.
"""

import requests
from src.models.corp.regiao_geografica import RegiaoGeografica
from src.core.validacoes import validar_e_devolver_cep

BRASILAPI_CEP_URL = "https://brasilapi.com.br/api/cep/v2/{cep}"
VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
CEP_TIMEOUT_SEGUNDOS = 5


# Cache em memória de CEP -> dados já resolvidos, para não bater a API
# de novo para o mesmo CEP (útil já que muitos pacientes/empresas
# compartilham o mesmo CEP). Cache é por processo, igual ao de
# centroides de município -- em ambiente com múltiplos workers, cada
# worker mantém o seu próprio cache independente. Guarda o resultado
# completo (dict ou None) para não repetir a lógica de fallback.
_cache_endereco_por_cep: dict = {}


class CepService:

    def regiao_por_cep(self, cep: str) -> RegiaoGeografica | None:
        from src.domains.regiao.service import RegiaoService

        codigo_ibge = self.buscar_codigo_ibge_por_cep(cep)

        regiao_service = RegiaoService()

        return regiao_service.buscar_ou_criar_por_codigo_ibge(codigo_ibge) if codigo_ibge else None

    def buscar_endereco_por_cep(self, cep: str) -> dict | None:
        """
        Consulta o CEP (BrasilAPI primeiro, ViaCEP como fallback) e
        devolve {"bairro": str | None, "codigo_ibge": str | None,
        "latitude": float | None, "longitude": float | None}, ou None
        se o CEP for inválido em formato, não existir, ou se ambas as
        fontes falharem.

        Resultado é cacheado em memória por CEP, incluindo o caso de
        "não encontrado", para não reconsultar repetidamente um CEP
        que já se sabe inválido/inexistente.
        """

        cep_limpo = validar_e_devolver_cep(cep)
        if cep_limpo is None:
            return None

        if cep_limpo in _cache_endereco_por_cep:
            return _cache_endereco_por_cep[cep_limpo]

        resultado = self._consultar_brasilapi(cep_limpo)
        if resultado is None:
            resultado = self._consultar_viacep(cep_limpo)

        _cache_endereco_por_cep[cep_limpo] = resultado
        return resultado

    def buscar_bairro_por_cep(self, cep: str) -> str | None:
        """Atalho para quem só precisa do bairro."""
        endereco = self.buscar_endereco_por_cep(cep)
        return endereco["bairro"] if endereco else None

    def buscar_codigo_ibge_por_cep(self, cep: str) -> str | None:
        """Atalho para quem só precisa do código IBGE do município."""
        endereco = self.buscar_endereco_por_cep(cep)
        return endereco["codigo_ibge"] if endereco else None

    def buscar_coordenadas_por_cep(self, cep: str) -> dict | None:
        """
        Atalho para quem só precisa das coordenadas do CEP. Devolve
        {"latitude": float, "longitude": float}, ou None se o CEP for
        inválido/inexistente ou se as coordenadas não estiverem
        disponíveis (ex: quando o resultado veio do fallback ViaCEP,
        que não devolve coordenadas).
        """
        endereco = self.buscar_endereco_por_cep(cep)
        if not endereco or endereco["latitude"] is None or endereco["longitude"] is None:
            return None
        return {"latitude": endereco["latitude"], "longitude": endereco["longitude"]}

    def _consultar_brasilapi(self, cep_limpo: str) -> dict | None:
        """
        Fonte primária. Devolve bairro, codigo_ibge (a partir de
        `ibge.city`) e coordenadas (a partir de `location.coordinates`,
        quando presentes -- nem todo CEP tem coordenadas na BrasilAPI).
        """
        
        url = BRASILAPI_CEP_URL.format(cep=cep_limpo)

        try:
            resposta = requests.get(url, timeout=CEP_TIMEOUT_SEGUNDOS)
        except requests.RequestException:
            return None

        if resposta.status_code != 200:
            return None

        try:
            dados = resposta.json()

            bairro = dados.get("neighborhood")

            codigo_ibge = None
            ibge = dados.get("ibge")
            if isinstance(ibge, dict):
                codigo_ibge_bruto = ibge.get("city")
                codigo_ibge = str(codigo_ibge_bruto) if codigo_ibge_bruto else None

            latitude = None
            longitude = None
            location = dados.get("location")
            if isinstance(location, dict):
                coordinates = location.get("coordinates")
                if isinstance(coordinates, dict):
                    try:
                        lat_bruta = coordinates.get("latitude")
                        lon_bruta = coordinates.get("longitude")
                        latitude = float(lat_bruta) if lat_bruta not in (None, "") else None
                        longitude = float(lon_bruta) if lon_bruta not in (None, "") else None
                    except (ValueError, TypeError):
                        latitude = None
                        longitude = None

            return {
                "bairro": bairro if bairro else None,
                "codigo_ibge": codigo_ibge,
                "latitude": latitude,
                "longitude": longitude,
            }
        except (ValueError, TypeError, AttributeError):
            return None

    def _consultar_viacep(self, cep_limpo: str) -> dict | None:
        """
        Fallback usado só quando a BrasilAPI falha/não responde. Não
        devolve coordenadas -- o ViaCEP não traz esse dado no payload
        (ao contrário da BrasilAPI v2).
        """
        url = VIACEP_URL.format(cep=cep_limpo)

        try:
            resposta = requests.get(url, timeout=CEP_TIMEOUT_SEGUNDOS)
        except requests.RequestException:
            return None

        if resposta.status_code != 200:
            return None

        try:
            dados = resposta.json()
            # ViaCEP devolve 200 com {"erro": true} para CEP
            # inexistente (não usa status HTTP 404 nesse caso).
            if dados.get("erro"):
                return None

            bairro = dados.get("bairro")
            codigo_ibge = dados.get("ibge")
            return {
                "bairro": bairro if bairro else None,
                "codigo_ibge": codigo_ibge if codigo_ibge else None,
                "latitude": None,
                "longitude": None,
            }
        except (ValueError, TypeError, AttributeError):
            return None