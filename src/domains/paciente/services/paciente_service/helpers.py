"""Funções e constantes de módulo usadas pelos mixins do PacienteService."""
import unicodedata
from datetime import datetime, date

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import DadosInvalidosError


def _normalizar(texto: str) -> str:
    """Minúsculo e sem acento, para busca por nome."""
    sem_acento = unicodedata.normalize("NFD", texto or "")
    return "".join(ch for ch in sem_acento if unicodedata.category(ch) != "Mn").lower().strip()

def _parse_data(valor):
    """Aceita date/datetime já convertidos ou string ISO 'YYYY-MM-DD' vinda do JSON."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")


_CONSTRAINT_CPF_EMPRESA = "uq_paciente_pessoal_empresa_cpf"


def _violou_cpf_unico(e: IntegrityError) -> bool:
    """True só quando o IntegrityError é a UNIQUE (id_empresa, cpf_hash).
    Qualquer outra violação (FK, enum, NOT NULL) NÃO pode ser traduzida
    para "CPF duplicado": esconderia o erro real. O nome da constraint
    aparece na mensagem do driver tanto no MySQL quanto no Postgres."""
    return _CONSTRAINT_CPF_EMPRESA in str(getattr(e, "orig", e))
