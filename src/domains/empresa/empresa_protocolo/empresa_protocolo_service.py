"""
empresa_protocolo_service.py

Regras de negócio da liberação institucional de protocolos. Decide quais
protocolos do catálogo cada empresa libera, sua política (obrigatório ou
opcional) e qual é o padrão institucional por escopo de uso. Toda liberação,
bloqueio ou troca de padrão registra quem aprovou e quando; o aprovador é
sempre lido da sessão e nunca do payload, pois é um dado que quem está agindo
não deveria conseguir forjar. Também garante os invariantes da governança
clínica: protocolo obrigatório precisa estar ativo, o padrão institucional não
pode ser desativado e a empresa mantém um mínimo de protocolos ativos.
"""

from datetime import datetime, timezone

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from src.core.session import get_id_usuario_sessao
from src.core.erros_pydantic import erros_pydantic_por_campo
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
        """Converte o uuid (que a página conhece) no protocolo do catálogo.
        O id numérico fica interno ao back; as rotas falam uuid.

        Raises:
            RecursoNaoEncontradoError: uuid inexistente no catálogo.
        """
        catalogo = self.repo_catalogo.find_by_uuid(uuid_protocolo)
        if not catalogo:
            raise RecursoNaoEncontradoError("Protocolo não encontrado.")
        return catalogo

    def listar_para_empresa(self, id_empresa: int):
        """Cruza o catálogo inteiro com os vínculos da empresa.

        Protocolos nunca tocados aparecem com vinculo=None ("não liberado") em
        vez de ficarem ausentes.

        Returns:
            Lista de {"protocolo": <catálogo>, "vinculo": <EmpresaProtocolo | None>}.
        """
        catalogo = self.repo_catalogo.find_all()
        vinculos = {v.id_protocolo_catalogo: v for v in self.repo.find_all_por_empresa(id_empresa)}
        return [
            {"protocolo": p, "vinculo": vinculos.get(p.id)}
            for p in catalogo
        ]

    def alterar_status(self, id_empresa: int, catalogo, dados: dict) -> EmpresaProtocolo:
        """Libera ou bloqueia um protocolo para a empresa e, opcionalmente, muda a política.

        Args:
            catalogo: protocolo do catálogo, obtido por resolver_catalogo (que
                garante a existência; não há segunda busca aqui).
            dados: {"ativo": bool, "politica": "obrigatorio"|"opcional" (opcional)}.
                Política omitida mantém a atual.

        Regras:
            - Obrigatório exige ativo=True; para desativar um obrigatório, enviar
              politica="opcional" junto.
            - O padrão institucional não pode ser desativado e a empresa mantém ao
              menos 2 protocolos ativos.
            - Grava aprovado_por (sessão) e aprovado_em.

        Raises:
            DadosInvalidosError, ConflictoError.
        """
        try:
            schema = AlterarStatusEmpresaProtocoloSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        vinculo = self.repo.find_por_empresa_e_protocolo(id_empresa, catalogo.id)

        # Vale para a política que ficaria no fim: a enviada agora ou, se omitida, a atual.
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
                id_protocolo_catalogo=catalogo.id,
            )

        vinculo.ativo = schema.ativo
        if schema.politica is not None:
            vinculo.politica = schema.politica
        vinculo.aprovado_por = get_id_usuario_sessao()
        vinculo.aprovado_em = datetime.now(timezone.utc)

        return self.repo.save(vinculo)

    def definir_default_institucional(self, id_empresa: int, catalogo, dados: dict) -> EmpresaProtocolo:
        """Define o protocolo como padrão institucional de um escopo.

        Args:
            catalogo: protocolo do catálogo, obtido por resolver_catalogo (que
                garante a existência; não há segunda busca aqui).
            dados: {"escopo": "triagem"|"consulta"|"ambos"}.

        Regras:
            - O protocolo precisa estar ativo para a empresa.
            - Precisa servir ao escopo: um de triagem não vira padrão de consulta,
              e "ambos" só vale para protocolos de uso "ambos".
            - Cada vínculo tem UM slot de padrão; mover de um escopo para outro
              exige antes definir outro padrão no escopo de origem.
            - Se o escopo já tinha outro padrão, ele perde o slot na mesma
              transação (e também registra aprovado_por/aprovado_em).

        Raises:
            DadosInvalidosError, ConflictoError.
        """
        try:
            schema = DefinirDefaultInstitucionalSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        vinculo = self.repo.find_por_empresa_e_protocolo(id_empresa, catalogo.id)
        if not vinculo or not vinculo.ativo:
            raise DadosInvalidosError("Só é possível definir como default um protocolo ativo para a empresa.")

        if catalogo.escopo_uso not in (schema.escopo, "ambos"):
            raise DadosInvalidosError("Este protocolo não se aplica ao escopo escolhido.")

        atual = vinculo.escopo_default_institucional
        if atual is not None and atual != schema.escopo:
            raise ConflictoError(
                f"Este protocolo já é o padrão de '{atual}'. Defina outro padrão "
                "para esse escopo antes de movê-lo.")

        quem = get_id_usuario_sessao()
        agora = datetime.now(timezone.utc)

        anterior = self.repo.find_default_do_escopo(id_empresa, schema.escopo)
        if anterior and anterior.id_protocolo_catalogo != catalogo.id:
            anterior.escopo_default_institucional = None
            anterior.aprovado_por = quem
            anterior.aprovado_em = agora
            self.repo.save(anterior, commit=False)  # mesma transação da troca

        vinculo.escopo_default_institucional = schema.escopo
        vinculo.aprovado_por = quem
        vinculo.aprovado_em = agora
        return self.repo.save(vinculo)

    def _garantir_minimo_dois_ativos(self, id_empresa: int, vinculo_alvo: EmpresaProtocolo | None):
        """Impede desativar o padrão institucional ou deixar a empresa com menos de 2 protocolos ativos.

        Raises:
            ConflictoError: se a desativação violar uma dessas regras.
        """
        if vinculo_alvo and vinculo_alvo.escopo_default_institucional is not None:
            raise ConflictoError("O protocolo padrão da empresa não pode ser desativado.")

        ativos = self.repo.contar_ativos(id_empresa)
        ja_estava_ativo = vinculo_alvo is not None and vinculo_alvo.ativo
        if ja_estava_ativo and ativos <= 2:
            raise ConflictoError("A empresa precisa manter ao menos 2 protocolos ativos.")