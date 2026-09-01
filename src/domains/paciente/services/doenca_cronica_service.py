from datetime import datetime, timezone, date

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, DoencaCronicaRepository
from src.schemas.schema_doenca_cronica import DoencaCronicaCreateSchema, _formatar_erros_pydantic

def _parse_data(valor):
    """Aceita date/datetime já convertidos ou string ISO 'YYYY-MM-DD' vinda do JSON."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")
    
class DoencaCronicaService:
    """Doenças crônicas do paciente."""

    def __init__(self):
        self.repo = DoencaCronicaRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        p = self.paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def listar_doencas(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    def adicionar_doenca(self, uuid_paciente: str, dados: dict, id_empresa: int):
        """ALTERADO: validação movida para DoencaCronicaCreateSchema
        (Pydantic) -- antes checava só presença, não o valor de
        `status` contra o Enum do banco (ativa|em-remissao)."""
        from src.models.pacientes import DoencaCronica
        p = self._paciente_ou_404(uuid_paciente, id_empresa)

        try:
            entrada = DoencaCronicaCreateSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        d = DoencaCronica(
            id_paciente=p.id,
            codigo_cid10=entrada.codigo_cid10,
            descricao_cid10=entrada.descricao_cid10,
            desde=entrada.desde,
            status=entrada.status,
            observacoes=entrada.observacoes,
        )
        return self.repo.save(d)

    # --- F1: Doenças crônicas mais comuns na base ---
    def top_cid_ativas(self, id_empresa: int, limite: int = 10):
        return self.repo.top_cid_ativas(id_empresa=id_empresa, limite=limite)