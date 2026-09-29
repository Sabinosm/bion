"""Regras de negócio de EmpresaProtocolo: liberação institucional de protocolos.

Todo protocolo liberado ou bloqueado exige aprovado_por (governança clínica),
lido da sessão -- nunca aceito via payload, pelo mesmo motivo que
AtualizacaoEmpresaSchema bloqueia cnpj/status_plano: é um dado que a própria
ponta que está agindo não deveria conseguir forjar.
"""

from datetime import datetime, timezone

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

    def resolver_catalogo(self, uuid_protocolo: str):
        """uuid (o que a página conhece) -> protocolo do catálogo. O id numérico
        fica interno ao back; as rotas falam uuid."""
        catalogo = self.repo_catalogo.find_by_uuid(uuid_protocolo)
        if not catalogo:
            raise RecursoNaoEncontradoError("Protocolo não encontrado.")
        return catalogo

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

        # Convenção 2 do model: 'obrigatorio' exige ativo=1. Vale para a política
        # que ficaria no fim (a enviada agora ou, se omitida, a atual). Para
        # desativar um obrigatório, mande politica="opcional" junto.
        politica_final = schema.politica if schema.politica is not None else (
            vinculo.politica if vinculo else "opcional")
        if not schema.ativo and politica_final == "obrigatorio":
            raise DadosInvalidosError(
                "Um protocolo obrigatório precisa estar ativo. "
                "Torne-o opcional antes de desativá-lo.")

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
        # Convenção 3 do model: mudança de ativo/política exige quem e quando.
        vinculo.aprovado_por = get_id_usuario_sessao()
        vinculo.aprovado_em = datetime.now(timezone.utc)

        return self.repo.save(vinculo)

    def definir_default_institucional(self, id_empresa: int, id_protocolo_catalogo: int, dados: dict) -> EmpresaProtocolo:
        try:
            schema = DefinirDefaultInstitucionalSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        catalogo = self.repo_catalogo.find_by_id(id_protocolo_catalogo)
        if not catalogo:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {id_protocolo_catalogo}")

        vinculo = self.repo.find_por_empresa_e_protocolo(id_empresa, id_protocolo_catalogo)
        if not vinculo or not vinculo.ativo:
            raise DadosInvalidosError("Só é possível definir como default um protocolo ativo para a empresa.")

        # O protocolo precisa servir ao escopo: um de triagem não vira default de
        # consulta, e "ambos" só vale para protocolos de uso "ambos".
        if catalogo.escopo_uso not in (schema.escopo, "ambos"):
            raise DadosInvalidosError("Este protocolo não se aplica ao escopo escolhido.")

        # Cada vínculo tem UM slot de default. Mover o padrão de um escopo para
        # outro deixaria o escopo de origem sem padrão -- exige definir outro antes.
        atual = vinculo.escopo_default_institucional
        if atual is not None and atual != schema.escopo:
            raise ConflictoError(
                f"Este protocolo já é o padrão de '{atual}'. Defina outro padrão "
                "para esse escopo antes de movê-lo.")

        # Convenção 3 do model: mudança de default institucional exige quem e quando
        # (vale também para o protocolo que perde o slot).
        quem = get_id_usuario_sessao()
        agora = datetime.now(timezone.utc)

        anterior = self.repo.find_default_do_escopo(id_empresa, schema.escopo)
        if anterior and anterior.id_protocolo_catalogo != id_protocolo_catalogo:
            anterior.escopo_default_institucional = None
            anterior.aprovado_por = quem
            anterior.aprovado_em = agora
            self.repo.save(anterior, commit=False)  # mesma transação da troca

        vinculo.escopo_default_institucional = schema.escopo
        vinculo.aprovado_por = quem
        vinculo.aprovado_em = agora
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