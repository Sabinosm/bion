"""protocolo_catalogo_service.py

Regras de negócio do catálogo de protocolos: cadastro, consultas simples e
montagem dos resumos exibidos nos cards da página de catálogo, combinando o
protocolo com a liberação da empresa e com o estado pessoal (favorito/padrão)
do profissional logado.
"""
from datetime import date, datetime

from src.core.exceptions import DadosInvalidosError, RecursoNaoEncontradoError
from src.models.protocolos import ProtocoloCatalogo

from ..repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository

CAMPOS_OBRIGATORIOS_PROTOCOLO = (
    "nome_protocolo", "sigla", "tipo_resultado", "versao_vigente", "data_vigencia",
)
FUNCOES_COM_FAVORITOS = ("medico", "enfermeiro")


def parse_data(valor):
    """Converte 'YYYY-MM-DD' em date. Aceita date ou None e os devolve sem alteração.

    Raises:
        DadosInvalidosError: se o valor não estiver no formato esperado.
    """
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")


class ProtocoloCatalogoService:

    def __init__(self):
        self.repo = ProtocoloCatalogoRepository()

    def buscar_por_uuid(self, uuid: str) -> ProtocoloCatalogo:
        """Retorna o protocolo pelo UUID.

        Raises:
            RecursoNaoEncontradoError: se não existir.
        """
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {uuid}")
        return e

    def buscar_por_uuid_e_tipo(self, uuid: str, tipo_protocolo: str) -> ProtocoloCatalogo:
        """Retorna o protocolo pelo UUID, garantindo que seja do tipo esperado.

        Usado pelas rotas de cada família para que o protocolo de uma família
        nunca seja consultado ou executado pela rota de outra.

        Raises:
            RecursoNaoEncontradoError: se não existir.
            DadosInvalidosError: se o protocolo for de outro tipo.
        """
        protocolo = self.buscar_por_uuid(uuid)
        if protocolo.tipo_protocolo != tipo_protocolo:
            raise DadosInvalidosError(f"O protocolo '{protocolo.sigla}' não é do tipo '{tipo_protocolo}'.")
        return protocolo

    def buscar_por_id(self, id: int) -> ProtocoloCatalogo:
        """Retorna o protocolo pelo ID.

        Raises:
            RecursoNaoEncontradoError: se não existir.
        """
        e = self.repo.find_by_id(id)
        if not e:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {id}")
        return e

    def listar(self):
        """Lista todos os protocolos cadastrados."""
        return self.repo.find_all()

    def criar(self, dados: dict) -> ProtocoloCatalogo:
        """Cadastra um novo protocolo no catálogo.

        Raises:
            DadosInvalidosError: se faltar campo obrigatório, a data for inválida
                ou a sigla já existir.
        """
        faltando = [c for c in CAMPOS_OBRIGATORIOS_PROTOCOLO if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")
        if self.repo.find_by_sigla(dados["sigla"]):
            raise DadosInvalidosError(f"Já existe um protocolo com a sigla {dados['sigla']}.")

        protocolo = ProtocoloCatalogo(
            nome_protocolo=dados["nome_protocolo"],
            sigla=dados["sigla"],
            tipo_resultado=dados["tipo_resultado"],
            tipo_protocolo=dados.get("tipo_protocolo"),
            escopo_populacao=dados.get("escopo_populacao", "universal"),
            escopo_uso=dados.get("escopo_uso", "ambos"),
            versao_vigente=dados["versao_vigente"],
            data_vigencia=parse_data(dados["data_vigencia"]),
            referencia_bibliografica=dados.get("referencia_bibliografica"),
            orgao_emissor=dados.get("orgao_emissor"),
        )
        return self.repo.save(protocolo)

    def listar_catalogo(self, id_empresa: int) -> list[dict]:
        """Resumos de todo o catálogo ativo, com o status de liberação da empresa."""
        linhas = self.repo.find_all_com_status_empresa(id_empresa)
        return self.montar_resumos(id_empresa, linhas)

    def listar_catalogo_filtrado(
        self,
        id_empresa: int,
        tipo_protocolo: str = None,
        escopo_populacao: str = None,
        escopo_uso: str = None,
        apenas_liberados: bool = False,
        offset: int = 0,
    ) -> list[dict]:
        """Resumos do catálogo com filtros e paginação (ver o repository)."""
        linhas = self.repo.find_all_filtrado(
            id_empresa, tipo_protocolo, escopo_populacao, escopo_uso, apenas_liberados, offset
        )
        return self.montar_resumos(id_empresa, linhas)

    def detalhar(self, uuid: str, id_empresa: int) -> dict:
        """Detalhe do catálogo + resumo (liberação/favoritos) + versão ativa."""
        # Import local: o serviço de detalhe depende deste, então importar no topo cria ciclo.
        from .protocolo_detalhe_service import ProtocoloDetalheService
        return ProtocoloDetalheService().obter_detalhe(uuid, id_empresa)

    def montar_resumos(self, id_empresa: int, linhas) -> list[dict]:
        """Monta os resumos dos cards a partir de linhas (protocolo, ativo, politica).

        Busca UMA vez por requisição (fora do loop dos cards) o padrão
        institucional de cada protocolo e o estado pessoal (favorito/padrão)
        do profissional logado.
        """
        # Imports locais: evitam ciclo entre os domínios protocolo e configuracao.
        from src.core.session import get_usuario_sessao
        from src.domains.configuracao.service import ConfiguracaoService
        from src.domains.empresa.empresa_protocolo.empresa_protocolo_repository import EmpresaProtocoloRepository

        padroes = {
            v.id_protocolo_catalogo: v.escopo_default_institucional
            for v in EmpresaProtocoloRepository().find_all_por_empresa(id_empresa)
        }

        # Só médico/enfermeiro tem favoritos. Para os demais o mapa é None e os
        # campos pessoais saem null (o front não renderiza a estrela).
        usuario = get_usuario_sessao()
        clinico = bool(usuario and usuario.funcao_clinica in FUNCOES_COM_FAVORITOS)
        mapa = ConfiguracaoService().mapa_estado_pessoal(usuario.id) if clinico else None

        return [
            self._montar_resumo(
                protocolo, ativo, politica,
                escopo_default_institucional=padroes.get(protocolo.id),
                estado_pessoal=None if mapa is None else mapa.get(protocolo.id, {}),
            )
            for protocolo, ativo, politica in linhas
        ]

    @staticmethod
    def _montar_resumo(protocolo, ativo, politica,
                       escopo_default_institucional=None, estado_pessoal=None) -> dict:
        """DTO de resumo de um card, sem expor a estrutura interna do protocolo.

        `estado_pessoal`: None = usuário sem papel clínico (não tem favoritos);
        dict (possivelmente vazio) = profissional, com ou sem vínculo.
        """
        return {
            "uuid": protocolo.uuid,
            "nome_protocolo": protocolo.nome_protocolo,
            "sigla": protocolo.sigla,
            "tipo_protocolo": protocolo.tipo_protocolo,
            "escopo_populacao": protocolo.escopo_populacao,
            "escopo_uso": protocolo.escopo_uso,
            "liberado_pela_empresa": bool(ativo),
            "politica": politica,
            # Escopo em que é o padrão da instituição (trava a estrela cheia).
            "padrao_institucional": escopo_default_institucional,
            # null = sem papel clínico; true/false = favorito do profissional
            # (false cobre "nunca adicionou" e "pausado").
            "favorito": None if estado_pessoal is None else bool(estado_pessoal.get("em_uso")),
            # Escopo em que é o padrão pessoal, ou null.
            "default_pessoal": None if estado_pessoal is None else estado_pessoal.get("escopo_default"),
        }
