from datetime import datetime, timezone, date

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, DoencaCronicaRepository
from src.schemas.schema_doenca_cronica import (
    DoencaCronicaCreateSchema, DoencaCronicaAtualizarSchema,
    DoencaCronicaRemoverSchema, _formatar_erros_pydantic,
)

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
        `status` contra o Enum do banco (ativa|em-remissao).

        ALTERADO: checagem de posse explícita via _paciente_ou_404, que
        já filtra por id_empresa na busca do paciente -- garante que a
        doença só é criada se o paciente pertencer à empresa de quem
        chamou. Sem isso, um id_empresa "esquecido"/trocado permitiria
        criar doença crônica em paciente de outra empresa (mesmo risco
        multi-tenant que já existia em atualizar/remover)."""
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

    def atualizar_doenca(self, uuid_paciente: str, uuid_doenca: str, dados: dict, id_empresa: int):
        """NOVO: corrige/atualiza uma doença crônica já registrada
        (ex: mudar status de 'ativa' para 'em-remissao', corrigir CID
        digitado errado). Checagem de posse igual aos outros domínios
        clínicos -- confirma que a doença pertence a um paciente da
        empresa de quem chamou antes de aplicar qualquer alteração.

        ALTERADO: usa find_by_uuid_incluindo_deletados em vez de
        find_by_uuid -- precisa achar o registro mesmo se ele estiver
        soft-deletado, exatamente pra poder distinguir 'não existe'
        (404 genérico) de 'existe mas está deletado' (409 explícito,
        abaixo). Se usasse find_by_uuid normal, um registro deletado
        cairia direto no 404, o que esconderia a causa real do
        problema de quem está chamando a API."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        doenca = self.repo.find_by_uuid_incluindo_deletados(uuid_doenca)
        if not doenca or doenca.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Doença crônica não encontrada: {uuid_doenca}")
        if doenca.deletado:
            raise ConflictoError(
                f"Doença crônica removida não pode ser atualizada: {uuid_doenca}. "
                "Restaure o registro antes de editar."
            )

        try:
            entrada = DoencaCronicaAtualizarSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        for campo, valor in entrada.campos_informados().items():
            setattr(doenca, campo, valor)

        return self.repo.save(doenca)

    def remover_doenca(self, uuid_paciente: str, uuid_doenca: str, dados: dict, id_empresa: int):
        """NOVO: soft delete -- doença crônica é dado clínico histórico,
        não pode ser apagada fisicamente (auditoria/LGPD/responsabilidade
        médica). Motivo é obrigatório (validado via
        DoencaCronicaRemoverSchema) para deixar claro, em auditoria
        futura, por que o registro saiu da visão ativa (erro de
        digitação, duplicata, etc.) -- sem isso, um soft delete vira só
        um "sumiu" sem contexto. Mesma checagem de posse de
        atualizar_doenca: confirma que a doença pertence a um paciente
        da empresa de quem chamou antes de remover. find_by_uuid já
        filtra status='deletado', então tentar remover de novo um
        registro já removido cai aqui como 'não encontrado' --
        idempotente e sem vazar se já foi deletado antes ou nunca
        existiu."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        doenca = self.repo.find_by_uuid(uuid_doenca)
        if not doenca or doenca.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Doença crônica não encontrada: {uuid_doenca}")

        try:
            entrada = DoencaCronicaRemoverSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        return self.repo.soft_delete(doenca, entrada.motivo_delete, entrada.observacoes_delete)

    def restaurar_doenca(self, uuid_paciente: str, uuid_doenca: str, id_empresa: int):
        """NOVO: reverte um soft delete. Usa find_by_uuid_incluindo_deletados
        pelo mesmo motivo de atualizar_doenca -- precisa achar o
        registro mesmo estando deletado, já que é exatamente esse
        estado que a operação reverte. Casos:
        - não existe / não pertence ao paciente da empresa -> 404
        - existe mas NÃO está deletado -> 409, restaurar um registro
          já ativo não faz sentido e pode mascarar um clique duplicado
          do usuário ou uma race condition (não é idempotente como o
          soft_delete é -- lá "deletar de novo" é inofensivo, aqui
          "restaurar de novo" indicaria ordem de operações confusa)."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        doenca = self.repo.find_by_uuid_incluindo_deletados(uuid_doenca)
        if not doenca or doenca.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Doença crônica não encontrada: {uuid_doenca}")
        if not doenca.deletado:
            raise ConflictoError(
                f"Doença crônica não está removida, nada a restaurar: {uuid_doenca}"
            )

        return self.repo.restaurar(doenca)

    # --- F1: Doenças crônicas mais comuns na base ---
    def top_cid_ativas(self, id_empresa: int, limite: int = 10):
        return self.repo.top_cid_ativas(id_empresa=id_empresa, limite=limite)