
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
    
class ReacaoAlergiaService:
    """Alergias, doenças crônicas e medicamentos em uso do paciente."""

    def __init__(self):
        self.repo = ReacaoAlergiaRepository()
        self._alergia_repo = AlergiaRepository()

    def adicionar_reacao(self, uuid_alergia: str, dados: dict):
        """NOVO: registra reação adicional numa alergia já existente
        (histórico de ocorrências) -- caminho que não existia antes,
        já que o schema antigo só suportava uma reação por alergia."""
        alergia = self._alergia_repo.find_by_uuid(uuid_alergia)
        if not alergia:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        if not dados.get("manifestacao") or not dados.get("gravidade"):
            raise DadosInvalidosError("manifestacao e gravidade são obrigatórios.")
        alergia.registrar_reacao(
            manifestacao=dados["manifestacao"],
            gravidade=dados["gravidade"],
            descricao=dados.get("descricao"),
            data_ocorrencia=_parse_data(dados.get("data_ocorrencia")),
        )
        return self._alergia_repo.save(alergia)

    def remover_reacao(self, uuid_reacao: str):
        """Remove APENAS uma reação específica do histórico, mantendo a
        Alergia e as demais reações intactas -- uso: reação registrada
        por engano, diferente de remover a alergia toda."""
        removido = self.repo.delete_by_uuid(uuid_reacao)
        if not removido:
            raise RecursoNaoEncontradoError(f"Reação não encontrada: {uuid_reacao}")
        return removido


