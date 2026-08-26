
from datetime import datetime, timezone, date

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt, hmac_sha256
from ..repositories import (
    PacienteRepository, AlergiaRepository, ReacaoAlergiaRepository,
    DoencaCronicaRepository, MedicamentoEmUsoRepository, ConsentimentoRepository,
    ObservacaoTipoSanguineoRepository,
)

def _parse_data(valor):
    """Aceita date/datetime já convertidos ou string ISO 'YYYY-MM-DD' vinda do JSON."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")
    
class MedicamentoEmUsoService:
    """Alergias, doenças crônicas e medicamentos em uso do paciente."""

    def __init__(self):
        self.repo = MedicamentoEmUsoRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str):
        p = self.paciente_repo.find_by_uuid(uuid_paciente)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p
    
    def listar_medicamentos_em_uso(self, uuid_paciente: str):
        p = self._paciente_ou_404(uuid_paciente)
        return self.repo.find_por_paciente(p.id)

    def adicionar_medicamento_em_uso(self, uuid_paciente: str, dados: dict):
        from src.models.pacientes import MedicamentoEmUso
        p = self._paciente_ou_404(uuid_paciente)
        m = MedicamentoEmUso(
            id_paciente=p.id,
            id_catalogo=dados.get("id_catalogo"),
            descricao=dados.get("descricao"),
            dose=dados.get("dose"),
            frequencia=dados.get("frequencia"),
            desde=_parse_data(dados.get("desde")),
            flag_em_uso=bool(dados.get("flag_em_uso", True)),
            status_uso=dados.get("status_uso", "ativo" if dados.get("flag_em_uso", True) else "interrompido"),
        )
        return self.repo.save(m)
    