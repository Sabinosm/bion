"""Regras de negócio de EmpresaProtocolo: liberação institucional de protocolos.

Todo protocolo liberado ou bloqueado exige aprovado_por (governança clínica),
lido da sessão -- nunca aceito via payload, pelo mesmo motivo que
AtualizacaoEmpresaSchema bloqueia cnpj/status_plano: é um dado que a própria
ponta que está agindo não deveria conseguir forjar.
"""

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from src.core.session import get_id_usuario_sessao
from src.domains.usuario.schema_usuario import _formatar_erros_pydantic
from .empresa_protocolo_repository import EmpresaProtocoloRepository
from src.models.corp import EmpresaProtocolo
from .schema_empresa_protocolo import (
    AlterarStatusEmpresaProtocoloSchema,
    DefinirDefaultInstitucionalSchema,
)
from src.domains.protocolo.shared.repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository


class EmpresaProtocoloService:

    def __init__(self):
        self.repo = EmpresaProtocoloRepository()
        self.repo_catalogo = ProtocoloCatalogoRepository()

    def listar_para_empresa(self, id_empresa: int):
        """Cruza o catálogo inteiro com os vínculos já criados -- protocolos nunca
        tocados pela empresa aparecem como 'não liberado', não ficam ausentes da lista."""
        catalogo = self.repo_catalogo.find_all()
        vinculos = {v.id_protocolo_catalogo: v for v in self.repo.find_all_por_empresa(id_empresa)}
        return [
            {"protocolo": p, "vinculo": vinculos.get(p.id_protocolo_catalogo)}
            for p in catalogo
        ]

    def alterar_status(self, id_empresa: int, id_protocolo_catalogo: int, dados: dict) -> EmpresaProtocolo:
        try:
            schema = AlterarStatusEmpresaProtocoloSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        catalogo = self.repo_catalogo.find_by_id(id_protocolo_catalogo)
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {id_protocolo_catalogo}")

        vinculo = self.repo.find_por_empresa_e_protocolo(id_empresa, id_protocolo_catalogo)

        if not schema.ativo:
            self._garantir_minimo_dois_ativos(id_empresa, vinculo)

        if not vinculo:
            vinculo = EmpresaProtocolo(
                id_empresa=id_empresa,
                id_protocolo_catalogo=id_protocolo_catalogo,
            )

        vinculo.ativo = schema.ativo
        if schema.politica is not None:
            vinculo.politica = schema.politica
        vinculo.aprovado_por = get_id_usuario_sessao()

        return self.repo.save(vinculo)

    def definir_default_institucional(self, id_empresa: int, id_protocolo_catalogo: int, dados: dict) -> EmpresaProtocolo:
        try:
            schema = DefinirDefaultInstitucionalSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        vinculo = self.repo.find_por_empresa_e_protocolo(id_empresa, id_protocolo_catalogo)
        if not vinculo or not vinculo.ativo:
            raise DadosInvalidosError("Só é possível definir como default um protocolo ativo para a empresa.")

        anterior = self.repo.find_default_do_escopo(id_empresa, schema.escopo)
        if anterior and anterior.id_protocolo_catalogo != id_protocolo_catalogo:
            anterior.escopo_default_institucional = None
            self.repo.save(anterior, commit=False)

        vinculo.escopo_default_institucional = schema.escopo
        return self.repo.save(vinculo)

    def _garantir_minimo_dois_ativos(self, id_empresa: int, vinculo_alvo: EmpresaProtocolo | None):
        """A empresa sempre mantém ao menos 2 protocolos ativos, e o default
        institucional nunca pode ser desativado (decisão já registrada no
        planejamento do domínio de protocolos)."""
        if vinculo_alvo and vinculo_alvo.escopo_default_institucional is not None:
            raise ConflictoError("O protocolo padrão da empresa não pode ser desativado.")

        ativos = self.repo.contar_ativos(id_empresa)
        ja_estava_ativo = vinculo_alvo is not None and vinculo_alvo.ativo
        if ja_estava_ativo and ativos <= 2:
            raise ConflictoError("A empresa precisa manter ao menos 2 protocolos ativos.")