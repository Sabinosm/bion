from .alergia import Alergia
from .reacao_alergia import ReacaoAlergia
from .consentimento import Consentimento
from .observacao_tipo_sanguineo import ObservacaoTipoSanguineo
from .doenca_cronica import DoencaCronica
from .medicamento_em_uso import MedicamentoEmUso
from .paciente import Paciente
from .paciente_dados_pessoais import PacienteDadosPessoais

__all__ = [
    "Alergia",
    "ReacaoAlergia",
    "Consentimento",
    "DoencaCronica",
    "MedicamentoEmUso",
    "Paciente",
    "PacienteDadosPessoais",
    "ObservacaoTipoSanguineo"
]