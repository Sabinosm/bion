from datetime import datetime, timezone

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, ConsentimentoRepository
from src.schemas.schema_consentimento import ConsentimentoCreateSchema, _formatar_erros_pydantic

class ConsentimentoService:

    def __init__(self):
        self.repo = ConsentimentoRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        p = self.paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def listar_por_paciente(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    def registrar(self, uuid_paciente: str, dados: dict, id_usuario_coletor: int, id_empresa: int):
        """ALTERADO: validação movida para ConsentimentoCreateSchema --
        antes checava só presença de versao_termo/canal_coleta, não se
        canal_coleta batia com o Enum do banco
        (presencial-papel|presencial-digital|portal-online|totem)."""
        from src.models.pacientes import Consentimento
        p = self._paciente_ou_404(uuid_paciente, id_empresa)

        try:
            entrada = ConsentimentoCreateSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        ativo = self.repo.find_ativo_por_paciente(p.id)
        if ativo:
            ativo.status = "revogado"
            ativo.data_revogacao = datetime.now(timezone.utc)
            ativo.motivo_revogacao = "Substituído por novo termo de consentimento."
            self.repo.save(ativo)

        c = Consentimento(
            id_paciente=p.id,
            coletado_por=id_usuario_coletor,
            versao_termo=entrada.versao_termo,
            data_consentimento=datetime.now(timezone.utc),
            canal_coleta=entrada.canal_coleta,
            escopo_consentimento_json=entrada.escopo_consentimento,
            hash_documento=entrada.hash_documento,
        )
        return self.repo.save(c)

    def revogar(self, uuid_paciente: str, motivo: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        ativo = self.repo.find_ativo_por_paciente(p.id)
        if not ativo:
            raise RecursoNaoEncontradoError("Não há consentimento ativo para este paciente.")
        ativo.status = "revogado"
        ativo.data_revogacao = datetime.now(timezone.utc)
        ativo.motivo_revogacao = motivo or "Revogado a pedido do titular."
        return self.repo.save(ativo)