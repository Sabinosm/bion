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

    def criar_a_partir_de_fhir(self, practitioner, id_empresa: int, tipo_usuario: str, user_login: str = None) -> dict:
        """POST /fhir/Practitioner -- caminho INBOUND.

        Parâmetros:
            practitioner: instância de fhir.resources.R4B.practitioner.Practitioner,
                já validada pela rota antes de chegar aqui.
        """
        from src.domains.usuario.services.service import UsuarioService

        dados_base = fhir_practitioner_to_dados_cadastro(practitioner)
        dados_base["tipo_usuario"] = tipo_usuario
        if user_login:
            dados_base["user_login"] = user_login

        if tipo_usuario in ("medico", "enfermeiro"):
            raise ValueError(
                f"Criar Practitioner do tipo '{tipo_usuario}' exige dados de "
                "CRM/COREN (numero, UF, e para enfermeiro também especialidade), "
                "que não fazem parte do Resource Practitioner padrão. "
                "Use a rota interna de cadastro de usuário para este caso, "
                "ou aguarde a implementação de criação via Bundle "
                "(Practitioner + PractitionerRole) numa única transação."
            )

        usuario_service = UsuarioService()
        usuario = usuario_service.criar(id_empresa, dados_base, commitar=True)
        recurso = usuario_papel_to_fhir_practitioner(usuario, usuario.papel_ativo())
        return recurso.model_dump(exclude_none=True, mode="json")
