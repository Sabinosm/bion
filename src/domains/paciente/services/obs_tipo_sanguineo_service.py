
from datetime import datetime, timezone, date

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt, hmac_sha256
from ..repositories import (
    PacienteRepository, AlergiaRepository, ReacaoAlergiaRepository,
    DoencaCronicaRepository, MedicamentoEmUsoRepository, ConsentimentoRepository,
    ObservacaoTipoSanguineoRepository,
)

    
class ObservacaoTipoSanguineoService:
    """Alergias, doenças crônicas e medicamentos em uso do paciente."""

    def __init__(self):
        self.repo = ObservacaoTipoSanguineoRepository()
     
    # --- F3: Distribuição de tipo sanguíneo na base ---
    def distribuicao_tipo_sanguineo(self, id_empresa: int):
        return self.repo.distribuicao_tipo_sanguineo(id_empresa=id_empresa)