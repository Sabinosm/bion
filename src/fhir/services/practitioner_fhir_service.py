"""
Service de orquestração FHIR para Practitioner.

ATUALIZADO: mappers agora retornam instâncias de Practitioner
(fhir.resources), não dicts. Este service converte para dict na
FRONTEIRA (usando model_dump), para que a camada de rota/resposta HTTP
continue recebendo dict puro, sem precisar saber da existência da lib.
"""

from src.core.exceptions import RecursoNaoEncontradoError
from src.domains.usuario.repository import UsuarioRepository
from ._helpers import aplicar_elements
from ..mappers.practitioner_mapper import (
    usuario_papel_to_fhir_practitioner,
    fhir_practitioner_to_dados_cadastro,
)


class PractitionerFhirService:

    def __init__(self):
        self.usuario_repo = UsuarioRepository()

    def buscar_por_id(self, id_fhir: str, elements: list[str] | None = None) -> dict:
        """GET /fhir/Practitioner/{id} -- id_fhir é o UUID do Usuario."""
        usuario = self.usuario_repo.find_by_uuid(id_fhir)
        if not usuario:
            raise RecursoNaoEncontradoError(f"Practitioner não encontrado: {id_fhir}")

        papel = usuario.papel_ativo()
        recurso = usuario_papel_to_fhir_practitioner(usuario, papel)
        # model_dump(exclude_none=True): omite campos não preenchidos
        # do JSON de resposta, em vez de mandar "campo": null para tudo
        # que a lib inicializa como None por padrão.
        return aplicar_elements(recurso.model_dump(exclude_none=True, mode="json"), elements)

    def buscar_por_identifier(self, sistema: str, valor: str) -> list[dict]:
        """GET /fhir/Practitioner?identifier={sistema}|{valor}"""
        from ..mappers.practitioner_mapper import SYSTEM_CPF
        from src.core.security import hmac_sha256

        if sistema != SYSTEM_CPF:
            return []

        usuario = self.usuario_repo.find_by_cpf_hash(hmac_sha256(valor))
        if not usuario:
            return []
        recurso = usuario_papel_to_fhir_practitioner(usuario, usuario.papel_ativo())
        return [recurso.model_dump(exclude_none=True, mode="json")]

    def criar_a_partir_de_fhir(self, practitioner, id_empresa: int, user_login: str = None,
                                solicitante_eh_super_admin: bool = False) -> dict:
        """POST /fhir/Practitioner -- caminho INBOUND.

        ALTERADO (separação admin/papel clínico, decisão confirmada):
        antes recebia `tipo_usuario` e recusava explicitamente
        "medico"/"enfermeiro" (só "admin" funcionava, por falta de
        CRM/COREN no Resource Practitioner padrão). Como só um valor
        jamais dava certo, o parâmetro saiu -- esta função sempre cria
        um admin puro agora (eh_admin=True, sem função clínica).

        ADICIONADO: `solicitante_eh_super_admin` -- estava ausente
        antes (bug), e UsuarioService.criar() sempre exige esse
        parâmetro como True quando eh_admin=True (só o super admin cria
        outros admins). Sem repassá-lo, toda chamada falhava.

        Parâmetros:
            practitioner: instância de fhir.resources.R4B.practitioner.Practitioner,
                já validada pela rota antes de chegar aqui.
            solicitante_eh_super_admin: repassado direto para
                UsuarioService.criar() -- deve vir de g.is_super_admin
                na rota, nunca hardcoded ou inferido aqui.
        """
        from src.domains.usuario.services.service import UsuarioService

        dados_base = fhir_practitioner_to_dados_cadastro(practitioner)
        dados_base["eh_admin"] = True
        if user_login:
            dados_base["user_login"] = user_login

        usuario_service = UsuarioService()
        usuario = usuario_service.criar(
            id_empresa, dados_base, commitar=True,
            solicitante_eh_super_admin=solicitante_eh_super_admin,
        )
        recurso = usuario_papel_to_fhir_practitioner(usuario, usuario.papel_ativo())
        return recurso.model_dump(exclude_none=True, mode="json")