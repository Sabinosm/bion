"""Regras de negócio da entidade ProtocoloCatalogo."""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .repository import ProtocoloCatalogoRepository
from src.domains.protocolos_ia.helpers import parse_data

CAMPOS_OBRIGATORIOS_PROTOCOLO = (
    "nome_protocolo", "sigla", "tipo_resultado", "versao_vigente", "data_vigencia",
)


class ProtocoloCatalogoService:
    """Casos de uso de cadastro e consulta de ProtocoloCatalogo."""

    def __init__(self):
        self.repo = ProtocoloCatalogoRepository()

    def buscar_por_uuid(self, uuid: str):
        """Retorna um ProtocoloCatalogo pelo UUID ou lança RecursoNaoEncontradoError."""
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {uuid}")
        return e

    def buscar_por_id(self, id: int):
        """
        Retorna um ProtocoloCatalogo pelo ID.

        FIXME: método não lança RecursoNaoEncontradoError nem retorna `e`
        quando encontrado — corrigir para espelhar o comportamento de
        buscar_por_uuid antes de usar em produção.
        """
        e = self.repo.find_by_id(id)
        if not e:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado {id}")

    def listar(self):
        """Lista todos os ProtocoloCatalogo cadastrados."""
        return self.repo.find_all()

    def criar(self, dados: dict):
        """
        Cadastra um novo ProtocoloCatalogo.

        Raises:
            DadosInvalidosError: se faltar campo obrigatório ou a sigla já existir.
        """
        from src.models.protocolos import ProtocoloCatalogo

        faltando = [c for c in CAMPOS_OBRIGATORIOS_PROTOCOLO if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")
        if self.repo.find_by_sigla(dados["sigla"]):
            raise DadosInvalidosError(f"Já existe um protocolo com a sigla {dados['sigla']}.")

        p = ProtocoloCatalogo(
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
            flag_personalizado=bool(dados.get("flag_personalizado", False)),
        )
        return self.repo.save(p)
