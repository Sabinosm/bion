"""
service.py

Regras de negócio do domínio Região Geográfica: consulta, listagem e cadastro
de unidades territoriais, com ênfase em municípios identificados pelo código
IBGE. Quando um município ainda não existe no banco, ele é confirmado na API
pública de localidades do IBGE e cadastrado automaticamente, junto com a
população estimada (tabela de estimativas do IBGE) e o centroide (dataset
aberto de municípios, baixado uma vez por processo e guardado em memória).

As consultas externas são tolerantes a falha: erro de rede, tempo esgotado ou
resposta inesperada viram "sem dado" (None ou dicionário vazio), nunca exceção,
para uma indisponibilidade de terceiros não derrubar o fluxo de quem chamou. A
população e o centroide são dados "melhor com, mas não essenciais": sem eles a
região é criada mesmo assim.
"""

import csv
import io
import re
from typing import Optional

import requests

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from src.models.corp.regiao_geografica import RegiaoGeografica
from .repository import RegiaoRepository, PER_PAGE_PADRAO, limit_seguro


IBGE_MUNICIPIO_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo}"
IBGE_TIMEOUT_SEGUNDOS = 5

# Tabela SIDRA 6579 = "Estimativas da População" (pesquisa anual do IBGE,
# referência em 1º de julho de cada ano); variável 9324 = "População residente
# estimada". periodos/-1 pede sempre o último período disponível, então não é
# preciso fixar nem atualizar um ano manualmente no código.
IBGE_POPULACAO_URL = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/6579"
    "/periodos/-1/variaveis/9324?localidades=N6[{codigo}]"
)

# Fonte estática de centroides de município (lat/long): o IBGE não expõe um
# endpoint simples que devolva o ponto de centroide pronto (só a malha/polígono
# completo, que exigiria calcular o centroide geometricamente).
# kelvins/Municipios-Brasileiros é um dataset aberto (MIT), amplamente usado,
# com os 5.570 municípios e coordenadas derivadas do IBGE.
CENTROIDES_MUNICIPIOS_URL = (
    "https://raw.githubusercontent.com/kelvins/Municipios-Brasileiros/main/csv/municipios.csv"
)
CENTROIDES_TIMEOUT_SEGUNDOS = 10

# Código IBGE de município: sempre 7 dígitos.
_PADRAO_CODIGO_MUNICIPIO = re.compile(r"\d{7}")

_cache_centroides_municipios: Optional[dict] = None


def codigo_municipio_valido(codigo_ibge) -> bool:
    """True se o valor tem o formato de um código IBGE de município (7 dígitos)."""
    return isinstance(codigo_ibge, str) and _PADRAO_CODIGO_MUNICIPIO.fullmatch(codigo_ibge) is not None


def _obter_json(url: str, timeout: int):
    """GET que devolve o JSON da resposta, ou None se qualquer coisa der errado.

    Erro de rede, tempo esgotado, status diferente de 200 e corpo que não é
    JSON válido resultam todos em None.
    """
    try:
        resposta = requests.get(url, timeout=timeout)
    except requests.RequestException:
        return None

    if resposta.status_code != 200:
        return None

    try:
        return resposta.json()
    except ValueError:
        return None


class RegiaoService:

    def __init__(self):
        self.repo = RegiaoRepository()

    # ------------------------------------------------------------------
    # Consulta e cadastro
    # ------------------------------------------------------------------

    def buscar_por_id(self, id: int) -> RegiaoGeografica:
        r = self.repo.find_by_id(id)
        if not r:
            raise RecursoNaoEncontradoError(f"Região geográfica não encontrada: {id}")
        return r

    def buscar_por_uuid(self, uuid: str) -> RegiaoGeografica:
        r = self.repo.find_by_uuid(uuid)
        if not r:
            raise RecursoNaoEncontradoError(f"Região geográfica não encontrada: {uuid}")
        return r

    def buscar_por_codigo(self, codigo_ibge: str) -> RegiaoGeografica:
        """Região pelo código IBGE, só no banco. Levanta RecursoNaoEncontradoError se não existir."""
        regiao = self.repo.find_by_codigo_ibge(codigo_ibge)
        if not regiao:
            raise RecursoNaoEncontradoError(f"Região geográfica não encontrada: {codigo_ibge}")
        return regiao

    # Nome antigo, com acento, mantido como alias para quem ainda o chama.
    buscar_por_código = buscar_por_codigo

    def listar(self, tipo: Optional[str] = None) -> list:
        """Todas as regiões, ou só as de um tipo (ex.: "municipio") se informado."""
        if tipo:
            return self.repo.find_por_tipo(tipo)
        return self.repo.find_all()

    def listar_paginado(
        self, tipo: Optional[str] = None, page: int = 1, limit: int = PER_PAGE_PADRAO
    ) -> dict:
        """Uma página de regiões (15 por padrão), todas ou só de um tipo.

        Args:
            tipo: código do tipo de jurisdição (ex.: "municipio"), opcional.
            page: número da página, a partir de 1 (valores menores viram 1).
            limit: tamanho da página; vazio ou não positivo volta ao padrão e
                valores acima do máximo do repository são cortados.

        Returns:
            {"itens": [...], "total": int, "page": int, "limit": int}, com o
            `page` e o `limit` efetivamente usados.
        """
        page = max(page, 1)
        limit = limit_seguro(limit)
        itens, total = self.repo.find_paginado(tipo, page, limit)
        return {"itens": itens, "total": total, "page": page, "limit": limit}

    def criar(self, dados: dict) -> RegiaoGeografica:
        """Cadastra uma região a partir de um dicionário de dados.

        `tipo_regiao` é o código do tipo de jurisdição (ex.: "municipio") e é
        resolvido para a chave estrangeira; o tipo não pode ser passado direto
        ao construtor, pois na entidade é uma propriedade somente-leitura.

        Args:
            dados: obrigatórios `nome_regiao` e `tipo_regiao`; opcionais
                `codigo_ibge`, `uf`, `latitude_centroide`,
                `longitude_centroide` e `populacao_estimada`.

        Raises:
            DadosInvalidosError: se faltar campo obrigatório ou o tipo não existir.
        """
        if not dados.get("nome_regiao") or not dados.get("tipo_regiao"):
            raise DadosInvalidosError("nome_regiao e tipo_regiao são obrigatórios.")

        tipo_jurisdicao = self.repo.find_tipo_jurisdicao_por_codigo(dados["tipo_regiao"])
        if not tipo_jurisdicao:
            raise DadosInvalidosError(f"tipo_regiao inválido: {dados['tipo_regiao']}")

        r = RegiaoGeografica(
            nome_regiao=dados["nome_regiao"],
            id_tipo_jurisdicao=tipo_jurisdicao.id,
            codigo_ibge=dados.get("codigo_ibge"),
            uf=dados.get("uf"),
            latitude_centroide=dados.get("latitude_centroide"),
            longitude_centroide=dados.get("longitude_centroide"),
            populacao_estimada=dados.get("populacao_estimada"),
        )
        return self.repo.save(r)

    def buscar_ou_criar_por_codigo_ibge(self, codigo_ibge: str) -> Optional[RegiaoGeografica]:
        """Busca a região pelo código IBGE de município, cadastrando-a se ainda não existir.

        Se já existir no banco, devolve direto. Senão, confirma o código na API
        do IBGE e, se for válido, cadastra a região automaticamente (nome,
        código, UF, população estimada e centroide). Códigos fora do formato
        de 7 dígitos não chegam a ser consultados no IBGE.

        Erros de infraestrutura (rede, tempo esgotado, resposta inesperada,
        falha ao gravar) não quebram o fluxo de quem chamou: viram None. Se a
        gravação falhar, a transação é desfeita e a região é procurada de
        novo, porque outra requisição pode tê-la cadastrado no meio-tempo.

        Returns:
            A região encontrada ou criada, ou None se o código não existir no
            IBGE, tiver formato inválido ou a consulta falhar.
        """
        regiao_existente = self.repo.find_by_codigo_ibge(codigo_ibge)
        if regiao_existente:
            return regiao_existente

        if not codigo_municipio_valido(codigo_ibge):
            return None

        dados_ibge = self._consultar_municipio_ibge(codigo_ibge)
        if dados_ibge is None:
            return None

        # Sem o tipo "municipio" na tabela de referência não dá para persistir
        # a região corretamente; não é um problema do código IBGE em si.
        tipo_municipio = self.repo.find_tipo_jurisdicao_por_codigo("municipio")
        if not tipo_municipio:
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
            self.repo.rollback()
            return self.repo.find_by_codigo_ibge(dados_ibge["codigo_ibge"])

    # ------------------------------------------------------------------
    # Consultas externas (tolerantes a falha)
    # ------------------------------------------------------------------

    def _consultar_municipio_ibge(self, codigo_ibge: str) -> Optional[dict]:
        """Consulta o município na API de localidades do IBGE.

        Returns:
            {"nome", "codigo_ibge", "uf"}, ou None se o código não existir ou
            qualquer coisa der errado (rede, tempo esgotado, JSON inesperado).
        """
        dados = _obter_json(IBGE_MUNICIPIO_URL.format(codigo=codigo_ibge), IBGE_TIMEOUT_SEGUNDOS)
        if dados is None:
            return None

        try:
            return {
                "nome": dados["nome"],
                "codigo_ibge": str(dados["id"]),
                "uf": dados["microrregiao"]["mesorregiao"]["UF"]["sigla"],
            }
        except (KeyError, TypeError):
            return None

    def _consultar_populacao_ibge(self, codigo_ibge: str) -> Optional[int]:
        """População estimada mais recente do município, na tabela SIDRA 6579.

        Returns:
            A população como int, ou None se a consulta falhar por qualquer
            motivo (inclusive quando o IBGE devolve valor não numérico).
        """
        dados = _obter_json(IBGE_POPULACAO_URL.format(codigo=codigo_ibge), IBGE_TIMEOUT_SEGUNDOS)
        if dados is None:
            return None

        try:
            series = dados[0]["resultados"][0]["series"][0]["serie"]
            # `serie` é {"<ano>": "<valor>"} com uma única chave (o ano do
            # último período); pega-se o único valor em vez de fixar o ano.
            return int(next(iter(series.values())))
        except (KeyError, IndexError, ValueError, TypeError, StopIteration):
            return None

    def _carregar_centroides_municipios(self) -> dict:
        """Centroides de todos os municípios, {codigo_ibge: {"latitude", "longitude"}}.

        O CSV (~5.570 linhas) é baixado uma vez por processo e guardado em
        memória no nível do módulo, já que raramente muda e baixá-lo a cada
        cadastro seria desperdício. Se o download ou a leitura falharem,
        devolve {} (sem guardar), e quem chama trata como "sem centroide".
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

    def _buscar_centroide_municipio(self, codigo_ibge: str) -> Optional[dict]:
        """Centroide do município, {"latitude", "longitude"}, ou None se não houver.

        Aproximação em nível de município: não substitui geocodificação fina
        por CEP ou endereço em análises que precisem de mais granularidade.
        """
        return self._carregar_centroides_municipios().get(codigo_ibge)