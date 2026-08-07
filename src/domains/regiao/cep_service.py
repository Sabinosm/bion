"""
Serviço utilitário de consulta de CEP.

Objetivo: resolver `bairro` e `codigo_ibge` a partir de um CEP, para
uso em agregações territoriais (ex: avaliação de endemias por bairro
ou por município) sem precisar reter/expor o CEP completo do
paciente/empresa em relatórios -- o CEP completo continua guardado
onde já está (Empresa, Paciente), este serviço só devolve o que for
pedido dele.

ESTRATÉGIA DE FONTE: ViaCEP como fonte primária (devolve bairro E
código IBGE no mesmo payload, sem esforço extra) com BrasilAPI como
fallback caso o ViaCEP falhe ou esteja fora do ar (BrasilAPI agrega
múltiplos provedores, então cobre boa parte dos casos em que o ViaCEP
sozinho falharia). Diferença de payload entre as duas fontes: a
BrasilAPI (v2) não devolve código IBGE diretamente -- por isso, quando
o fallback é usado, o resultado tem bairro mas pode não ter
codigo_ibge.

NOTA IMPORTANTE SOBRE PRIVACIDADE: mesmo bairro/município sendo uma
generalização do CEP, "bairro + condição de saúde" ainda pode ser dado
pessoal sensível dependendo do volume de casos naquele bairro (ver
k-anonimato). Este serviço só resolve CEP -> bairro/ibge; a decisão de
como agregar/expor isso em relatórios (ex: limiar mínimo de casos
antes de exibir) é responsabilidade de quem consome este serviço, não
deste módulo.
"""

import re
import requests
from src.models.corp.regiao_geografica import RegiaoGeografica
from src.core.validacoes import validar_cep

VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
BRASILAPI_CEP_URL = "https://brasilapi.com.br/api/cep/v2/{cep}"
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
        Consulta o CEP (ViaCEP primeiro, BrasilAPI como fallback) e
        devolve {"bairro": str | None, "codigo_ibge": str | None}, ou
        None se o CEP for inválido em formato, não existir, ou se
        ambas as fontes falharem.

        Resultado é cacheado em memória por CEP, incluindo o caso de
        "não encontrado", para não reconsultar repetidamente um CEP
        que já se sabe inválido/inexistente.
        """
        cep_limpo = validar_cep(cep)
        if cep_limpo is None:
            return None

        if cep_limpo in _cache_endereco_por_cep:
            return _cache_endereco_por_cep[cep_limpo]

        resultado = self._consultar_viacep(cep_limpo)
        if resultado is None:
            resultado = self._consultar_brasilapi(cep_limpo)

        _cache_endereco_por_cep[cep_limpo] = resultado
        return resultado

    def buscar_bairro_por_cep(self, cep: str) -> str | None:
        """Atalho para quem só precisa do bairro."""
        endereco = self.buscar_endereco_por_cep(cep)
        return endereco["bairro"] if endereco else None

    def buscar_codigo_ibge_por_cep(self, cep: str) -> str | None:
        """
        Atalho para quem só precisa do código IBGE do município. Só
        vem preenchido quando a fonte usada foi o ViaCEP (fonte
        primária) -- se a resposta veio do fallback BrasilAPI, este
        campo normalmente será None, já que a BrasilAPI (v2) não
        devolve o código IBGE no payload.
        """
        endereco = self.buscar_endereco_por_cep(cep)
        return endereco["codigo_ibge"] if endereco else None

    def _consultar_viacep(self, cep_limpo: str) -> dict | None:
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
            }
        except (ValueError, TypeError, AttributeError):
            return None

    def _consultar_brasilapi(self, cep_limpo: str) -> dict | None:
        """
        Fallback usado só quando o ViaCEP falha/não responde. Não
        devolve codigo_ibge -- a v2 da BrasilAPI não traz esse campo no
        payload (ao contrário do ViaCEP).
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
            return {
                "bairro": bairro if bairro else None,
                "codigo_ibge": None,
            }
        except (ValueError, TypeError, AttributeError):
            return None