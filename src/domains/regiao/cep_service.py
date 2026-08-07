"""
Serviço utilitário de consulta de CEP.

Objetivo principal: resolver `bairro` a partir de um CEP, para uso em
agregações territoriais mais finas que o município (ex: avaliação de
endemias por bairro) sem precisar reter/expor o CEP completo do
paciente/empresa em relatórios -- o CEP completo continua guardado
onde já está (Empresa, Paciente), este serviço só devolve o nome do
bairro para quem precisar dele.

"""

import re

import requests

BRASILAPI_CEP_URL = "https://brasilapi.com.br/api/cep/v2/{cep}"
BRASILAPI_TIMEOUT_SEGUNDOS = 5

REGEX_CEP_DIGITOS = re.compile(r"^\d{8}$")

# Cache em memória de CEP -> bairro já resolvido, para não bater a API
# de novo para o mesmo CEP (útil já que muitos pacientes/empresas
# compartilham o mesmo CEP). Cache é por processo, igual ao de
# centroides de município -- em ambiente com múltiplos workers, cada
# worker mantém o seu próprio cache independente.
_cache_bairro_por_cep: dict = {}


class CepService:

    def limpar_cep(self, cep: str) -> str | None:
        """
        Remove tudo que não for dígito e valida que sobraram exatamente
        8 dígitos (formato de CEP brasileiro). Devolve None se o valor
        não for um CEP válido em formato (não confirma se o CEP existe
        de fato -- isso só a consulta à API resolve).
        """
        if not cep:
            return None
        digitos = re.sub(r"\D", "", cep)
        return digitos if REGEX_CEP_DIGITOS.match(digitos) else None

    def buscar_bairro(self, cep: str) -> str | None:
        """
        Consulta o CEP na BrasilAPI (v2, com fallback entre provedores)
        e devolve só o nome do bairro, ou None se:
        - o CEP não for válido em formato;
        - o CEP não existir;
        - a consulta falhar por qualquer motivo (rede, timeout, resposta
          inesperada) -- erros de infraestrutura aqui não devem quebrar
          o fluxo de quem chamou, por isso viram None, não exceção.

        Resultado é cacheado em memória por CEP, incluindo o caso de
        "não encontrado", para não reconsultar repetidamente um CEP
        que já se sabe inválido/inexistente.
        """
        cep_limpo = self.limpar_cep(cep)
        if cep_limpo is None:
            return None

        if cep_limpo in _cache_bairro_por_cep:
            return _cache_bairro_por_cep[cep_limpo]

        bairro = self._consultar_bairro_brasilapi(cep_limpo)
        _cache_bairro_por_cep[cep_limpo] = bairro
        return bairro

    def _consultar_bairro_brasilapi(self, cep_limpo: str) -> str | None:
        url = BRASILAPI_CEP_URL.format(cep=cep_limpo)

        try:
            resposta = requests.get(url, timeout=BRASILAPI_TIMEOUT_SEGUNDOS)
        except requests.RequestException:
            return None

        if resposta.status_code != 200:
            return None

        try:
            dados = resposta.json()
            bairro = dados.get("neighborhood")
            # BrasilAPI pode devolver string vazia quando o provedor de
            # origem não tem o dado de bairro para aquele CEP (comum em
            # CEPs de zona rural/caixa postal) -- tratamos como
            # "não disponível", não como bairro válido.
            return bairro if bairro else None
        except (ValueError, TypeError, AttributeError):
            return None