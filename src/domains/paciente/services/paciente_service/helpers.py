"""helpers.py

Funções e constantes de módulo usadas pelos mixins do PacienteService:
normalização de texto para busca por nome, leitura de datas ISO e a
identificação da violação da UNIQUE de CPF por empresa.
"""
import unicodedata
from datetime import datetime, date

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import DadosInvalidosError
from src.domains.regiao.cep_service import CepService

_CONSTRAINT_CPF_EMPRESA = "uq_paciente_pessoal_empresa_cpf"


def _normalizar(texto: str) -> str:
    """Minúsculo e sem acento, para busca por nome."""
    sem_acento = unicodedata.normalize("NFD", texto or "")
    return "".join(ch for ch in sem_acento if unicodedata.category(ch) != "Mn").lower().strip()


def _parse_data(valor):
    """Aceita date/datetime já convertidos ou string ISO 'YYYY-MM-DD' vinda do JSON.

    Raises:
        DadosInvalidosError: se a string não estiver no formato esperado.
    """
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")


def _regiao_e_bairro_do_cep(cep, bairro=None):
    """Devolve (id_regiao_geografica, bairro) para um CEP. A região é sempre derivada do CEP; o
    `bairro` informado tem prioridade e só cai no bairro do CEP se vier ausente. Sem CEP, ambos
    ficam como vieram (região None). As duas consultas usam o mesmo cache em memória por CEP (uma
    só ida à API externa).

    Raises:
        DadosInvalidosError: CEP informado cuja região não foi resolvida.
    """
    id_regiao_geografica = None
    if cep:
        cep_service = CepService()
        regiao = cep_service.regiao_por_cep(cep)
        if regiao is None:
            raise DadosInvalidosError(
                "Não foi possível resolver a região geográfica a partir do CEP informado."
            )
        id_regiao_geografica = regiao.id_regiao_geografica
        if bairro is None:
            bairro = cep_service.buscar_bairro_por_cep(cep)
    return id_regiao_geografica, bairro


def _violou_cpf_unico(e: IntegrityError) -> bool:
    """True só quando o IntegrityError é a UNIQUE (id_empresa, cpf_hash).

    Qualquer outra violação (FK, enum, NOT NULL) NÃO pode ser traduzida para "CPF duplicado":
    esconderia o erro real. O nome da constraint aparece na mensagem do driver tanto no MySQL
    quanto no Postgres."""
    return _CONSTRAINT_CPF_EMPRESA in str(getattr(e, "orig", e))
