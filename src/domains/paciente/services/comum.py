"""comum.py

Funções compartilhadas pelos services de dados do paciente (alergia, reação,
doença crônica, medicamento em uso, tipo sanguíneo e consentimento): validação
de corpo com Pydantic, busca do paciente da empresa e execução com rollback
quando o próprio service é dono do commit.

A validação devolve o erro no formato do projeto: `message` curta e `erros`
com {campo: mensagem}, para o front pintar o input certo sem interpretar texto.
"""

from datetime import date, datetime, timezone

from pydantic import ValidationError

from src.core.erros_pydantic import erros_pydantic_por_campo
from src.core.exceptions import DadosInvalidosError, RecursoNaoEncontradoError


def validar_schema(schema, dados):
    """Valida `dados` com o schema Pydantic e devolve a instância.

    Raises:
        DadosInvalidosError: corpo que não é objeto JSON, ou erros do schema por campo.
    """
    if not isinstance(dados, dict):
        raise DadosInvalidosError("Corpo da requisição inválido: esperado um objeto JSON.")
    try:
        return schema(**dados)
    except ValidationError as e:
        raise DadosInvalidosError("Dados inválidos.", erros=erros_pydantic_por_campo(e))


def paciente_ou_404(paciente_repo, uuid_paciente: str, id_empresa: int):
    """Paciente da empresa pelo UUID. 404 igual para 'não existe' e 'é de outra empresa'.

    Raises:
        RecursoNaoEncontradoError: se não existir na empresa.
    """
    p = paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
    if not p:
        raise DadosInvalidosError(f"Paciente não encontrado: {uuid_paciente}")
    return p


def executar_com_rollback(repo, commit: bool, fn):
    """Executa `fn()`. Se o service é dono do commit (commit=True), desfaz tudo em caso de falha;
    com commit=False o rollback fica com quem controla a transação."""
    try:
        return fn()
    except Exception:
        if commit:
            repo.rollback()
        raise


def hoje_na_empresa(empresa_repo, id_empresa: int) -> date:
    """Data de HOJE no fuso da empresa (Empresa.fuso_horario; UTC se a empresa não for encontrada).
    Usada onde "hoje" é um padrão de negócio (data de mudança ou de encerramento), para o dia não
    virar horas antes ou depois do horário local."""
    empresa = empresa_repo.find_by_id(id_empresa)
    fuso = empresa.fuso_horario if empresa else timezone.utc
    return datetime.now(fuso).date()
