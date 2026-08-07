import csv
import io

import requests

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .repository import RegiaoRepository


IBGE_MUNICIPIO_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo}"
IBGE_TIMEOUT_SEGUNDOS = 5

# Tabela SIDRA 6579 = "Estimativas da População" (pesquisa anual do IBGE,
# data de referência 1º de julho de cada ano); variável 9324 = "População
# residente estimada". periodos/-1 pede sempre o último período disponível,
# então não precisamos fixar/atualizar um ano manualmente no código.
IBGE_POPULACAO_URL = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/6579"
    "/periodos/-1/variaveis/9324?localidades=N6[{codigo}]"
)

# Fonte estática de centroides de município (lat/long) -- o IBGE não
# expõe um endpoint simples que devolva um ponto de centroide pronto
# (só a malha/polígono completo, que exigiria calcular o centroide
# geometricamente). kelvins/Municipios-Brasileiros é um dataset aberto
# (MIT) amplamente usado, com os 5.570 municípios e coordenadas
# derivadas do IBGE. Baixado uma vez por processo e cacheado em
# memória -- ver _carregar_centroides_municipios.
CENTROIDES_MUNICIPIOS_URL = (
    "https://raw.githubusercontent.com/kelvins/Municipios-Brasileiros/main/csv/municipios.csv"
)
CENTROIDES_TIMEOUT_SEGUNDOS = 10

_cache_centroides_municipios: dict | None = None


class RegiaoService:

    def __init__(self):
        self.repo = RegiaoRepository()

    def buscar_por_uuid(self, uuid: str):
        r = self.repo.find_by_uuid(uuid)
        if not r:
            raise RecursoNaoEncontradoError(f"Região geográfica não encontrada: {uuid}")
        return r

    def listar(self, tipo: str = None):
        if tipo:
            return self.repo.find_por_tipo(tipo)
        return self.repo.find_all()

    def criar(self, dados: dict):
        """
        ALTERADO: RegiaoGeografica importada do módulo correto (estava
        vindo de src.models.corp.empresa por engano) e tipo_regiao
        resolvido via TipoJurisdicao -- não é mais possível passar
        tipo_regiao=... direto no construtor, já que virou @property
        somente-leitura (mesmo padrão de Empresa.cnpj / Usuario.tipo_usuario).
        """
        from src.models.corp.regiao_geografica import RegiaoGeografica
        from src.models.corp.tipo_jurisdicao import TipoJurisdicao

        if not dados.get("nome_regiao") or not dados.get("tipo_regiao"):
            raise DadosInvalidosError("nome_regiao e tipo_regiao são obrigatórios.")

        tipo_jurisdicao = TipoJurisdicao.query.filter_by(codigo=dados["tipo_regiao"]).first()
        if not tipo_jurisdicao:
            raise DadosInvalidosError(f"tipo_regiao inválido: {dados['tipo_regiao']}")

        r = RegiaoGeografica(
            nome_regiao=dados["nome_regiao"],
            id_tipo_jurisdicao=tipo_jurisdicao.id,
            id_regiao_pai=dados.get("id_regiao_pai"),
            codigo_ibge=dados.get("codigo_ibge"),
            uf=dados.get("uf"),
            latitude_centroide=dados.get("latitude_centroide"),
            longitude_centroide=dados.get("longitude_centroide"),
            populacao_estimada=dados.get("populacao_estimada"),
        )
        return self.repo.save(r)

    def buscar_por_código(self, codigo_ibge: str):
        regiao = self.repo.find_by_codigo_ibge(codigo_ibge)
        if not regiao:
            raise RecursoNaoEncontradoError(f"Região geográfica não encontrada: {codigo_ibge}")
        return regiao

    def buscar_ou_criar_por_codigo_ibge(self, codigo_ibge: str):
        """
        Busca a região pelo código IBGE de município. Se já existir no
        banco, retorna direto. Se não existir, consulta a API pública
        do IBGE para confirmar que o código é válido e, em caso
        positivo, cadastra a região automaticamente (nome, código e UF).

        Retorna a RegiaoGeografica encontrada/criada, ou None se o
        código não existir no IBGE ou se a consulta falhar por
        qualquer motivo (rede, timeout, resposta inesperada etc. --
        erros de infraestrutura aqui não devem quebrar o fluxo de quem
        chamou, por isso são engolidos e viram None, não exceção).
        """
        regiao_existente = self.repo.find_by_codigo_ibge(codigo_ibge)
        if regiao_existente:
            return regiao_existente

        dados_ibge = self._consultar_municipio_ibge(codigo_ibge)
        if dados_ibge is None:
            return None

        from src.models.corp.regiao_geografica import RegiaoGeografica
        from src.models.corp.tipo_jurisdicao import TipoJurisdicao

        tipo_municipio = TipoJurisdicao.query.filter_by(codigo="municipio").first()
        if not tipo_municipio:
            # Tabela de referência sem o tipo esperado cadastrado --
            # não é um problema do código IBGE em si, mas sem isso não
            # dá pra persistir a região corretamente.
            return None

        centroide = self._buscar_centroide_municipio(dados_ibge["codigo_ibge"])

        regiao = RegiaoGeografica(
            nome_regiao=dados_ibge["nome"],
            id_tipo_jurisdicao=tipo_municipio.id,
            codigo_ibge=dados_ibge["codigo_ibge"],
            uf=dados_ibge["uf"],
            populacao_estimada=self._consultar_populacao_ibge(dados_ibge["codigo_ibge"]),
            latitude_centroide=centroide["latitude"] if centroide else None,
            longitude_centroide=centroide["longitude"] if centroide else None,
        )

        try:
            return self.repo.save(regiao)
        except Exception:
            return None

    def _consultar_municipio_ibge(self, codigo_ibge: str) -> dict | None:
        """
        Chama a API pública de localidades do IBGE para um código de
        município e devolve um dict simplificado {nome, codigo_ibge, uf},
        ou None se o código não existir (404) ou se qualquer coisa der
        errado (rede, timeout, JSON inesperado etc).
        """
        url = IBGE_MUNICIPIO_URL.format(codigo=codigo_ibge)

        try:
            resposta = requests.get(url, timeout=IBGE_TIMEOUT_SEGUNDOS)
        except requests.RequestException:
            return None

        if resposta.status_code != 200:
            return None

        try:
            dados = resposta.json()
            uf_sigla = dados["microrregiao"]["mesorregiao"]["UF"]["sigla"]
            return {
                "nome": dados["nome"],
                "codigo_ibge": str(dados["id"]),
                "uf": uf_sigla,
            }
        except (KeyError, ValueError, TypeError):
            return None

    def _consultar_populacao_ibge(self, codigo_ibge: str) -> int | None:
        """
        Consulta a tabela SIDRA 6579 (Estimativas da População) para o
        município e devolve a população estimada mais recente como int,
        ou None se a consulta falhar por qualquer motivo -- população é
        um dado "melhor com, mas não essencial" aqui: se essa chamada
        falhar, a região ainda é criada normalmente sem ela (quem quiser
        pode tentar preencher depois).
        """
        url = IBGE_POPULACAO_URL.format(codigo=codigo_ibge)

        try:
            resposta = requests.get(url, timeout=IBGE_TIMEOUT_SEGUNDOS)
        except requests.RequestException:
            return None

        if resposta.status_code != 200:
            return None

        try:
            dados = resposta.json()
            series = dados[0]["resultados"][0]["series"][0]["serie"]
            # `serie` é um dict {"<ano>": "<valor>"} com uma única chave
            # (o ano do último período), então pegamos o único valor
            # presente em vez de fixar o ano no código.
            valor = next(iter(series.values()))
            return int(valor)
        except (KeyError, IndexError, ValueError, TypeError, StopIteration):
            return None

    def _carregar_centroides_municipios(self) -> dict:
        """
        Baixa o CSV de kelvins/Municipios-Brasileiros e devolve um dict
        {codigo_ibge (str): {"latitude": float, "longitude": float}}.

        Resultado é cacheado em memória no nível do módulo -- o arquivo
        tem ~5.570 linhas e não muda com frequência (municípios novos
        são raríssimos), então baixar uma vez por processo é suficiente
        e evita uma chamada HTTP a cada cadastro de região.

        Se o download falhar por qualquer motivo, devolve {} (dict
        vazio) em vez de lançar exceção -- quem chama trata isso como
        "sem centroide disponível", não como erro.
        """
        global _cache_centroides_municipios

        if _cache_centroides_municipios is not None:
            return _cache_centroides_municipios

        try:
            resposta = requests.get(CENTROIDES_MUNICIPIOS_URL, timeout=CENTROIDES_TIMEOUT_SEGUNDOS)
            resposta.raise_for_status()
        except requests.RequestException:
            return {}

        try:
            leitor = csv.DictReader(io.StringIO(resposta.text))
            centroides = {
                linha["codigo_ibge"]: {
                    "latitude": float(linha["latitude"]),
                    "longitude": float(linha["longitude"]),
                }
                for linha in leitor
            }
        except (KeyError, ValueError, TypeError):
            return {}

        _cache_centroides_municipios = centroides
        return centroides

    def _buscar_centroide_municipio(self, codigo_ibge: str) -> dict | None:
        """
        Devolve {"latitude": float, "longitude": float} do centroide do
        município (fonte estática, ver _carregar_centroides_municipios),
        ou None se o código não estiver na base ou se o download falhar.
        Aproximação de nível município -- não substitui geocoding fino
        por CEP/endereço para análises que precisem de mais granularidade.
        """
        centroides = self._carregar_centroides_municipios()
        return centroides.get(codigo_ibge)