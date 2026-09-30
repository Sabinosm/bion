"""Regras de negócio da entidade ProtocoloCatalogo."""

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ..repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository
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
        """Retorna um ProtocoloCatalogo pelo ID ou lança RecursoNaoEncontradoError."""
        e = self.repo.find_by_id(id)
        if not e:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado {id}")
        return e

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
        )
        return self.repo.save(p)
    
    # shared/services/protocolo_catalogo_service.py — métodos novos

    def listar_catalogo(self, id_empresa: int):
        """Página de catálogo, sem filtro -- visão geral com status de liberação."""
        linhas = self.repo.find_all_com_status_empresa(id_empresa)
        return self._montar_resumos(id_empresa, linhas)

    def listar_catalogo_filtrado(
        self,
        id_empresa: int,
        tipo_protocolo: str = None,
        escopo_populacao: str = None,
        escopo_uso: str = None,
        apenas_liberados: bool = False,
        offset: int = 0,
    ):
        linhas = self.repo.find_all_filtrado(
            id_empresa, tipo_protocolo, escopo_populacao, escopo_uso, apenas_liberados, offset
        )
        return self._montar_resumos(id_empresa, linhas)

    def _montar_resumos(self, id_empresa: int, linhas):
        """Monta os resumos da página juntando, UMA vez por requisição (fora do
        loop dos cards): o default institucional de cada protocolo e o estado
        pessoal (favorito/default) do profissional logado."""
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
        clinico = bool(usuario and usuario.funcao_clinica in ("medico", "enfermeiro"))
        mapa = ConfiguracaoService().mapa_estado_pessoal(usuario.id) if clinico else None

        return [
            self._montar_resumo(
                p, ativo, politica,
                escopo_default_institucional=padroes.get(p.id_protocolo_catalogo),
                estado_pessoal=None if mapa is None else mapa.get(p.id_protocolo_catalogo, {}),
            )
            for p, ativo, politica in linhas
        ]

    def _montar_resumo(self, protocolo, ativo, politica,
                       escopo_default_institucional=None, estado_pessoal=None):
        """DTO de resumo -- não expõe estrutura interna (JSON cru), só o
        necessário para o card da listagem. Detalhe completo é outra rota.

        estado_pessoal: None = usuário sem papel clínico (não tem favoritos);
        dict (possivelmente vazio) = profissional, com ou sem vínculo."""
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