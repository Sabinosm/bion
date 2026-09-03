from datetime import datetime, date

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, AlergiaRepository
from src.schemas.schema_alergia import (
    AlergiaCreateSchema, AlergiaAtualizarSchema, AlergiaRemoverSchema, _formatar_erros_pydantic,
)

def _parse_data(valor):
    """Aceita date/datetime já convertidos ou string ISO 'YYYY-MM-DD' vinda do JSON."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")
    
class AlergiaService:
    """Alergias do paciente (criação, listagem, remoção da alergia
    inteira, estatísticas).

    ALTERADO: adicionar_reacao/remover_reacao SAÍRAM daqui -- eram
    duplicados com ReacaoAlergiaService, que já cobre exatamente a
    mesma responsabilidade com o mesmo padrão (id_empresa, checagem de
    posse, schema Pydantic). Manter reação isolada num service próprio
    facilita mudar o comportamento de reação sem precisar tocar
    AlergiaService, e vice-versa."""

    def __init__(self):
        self.repo = AlergiaRepository()
        self._paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        """Isolamento de tenant -- ver histórico de mudanças anterior."""
        p = self._paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def listar_alergias(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)
 
    def adicionar_alergia(self, uuid_paciente: str, dados: dict, id_empresa: int):
        """ALTERADO: validação de obrigatórios + enum (gravidade,
        tipo_reacao) movida para AlergiaCreateSchema (Pydantic) --
        antes só checava presença via `not dados.get(...)`, sem checar
        se o VALOR de gravidade/tipo_reacao batia com o Enum do banco.
        Um valor fora do enum agora vira DadosInvalidosError (422) aqui,
        não IntegrityError cru do commit()."""
        from src.models.pacientes import Alergia
        p = self._paciente_ou_404(uuid_paciente, id_empresa)

        try:
            entrada = AlergiaCreateSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        a = Alergia(
            id_paciente=p.id,
            substancia=entrada.substancia,
            codigo_substancia=entrada.codigo_substancia,
            flag_confirmado=entrada.flag_confirmado,
        )
        a.registrar_reacao(
            manifestacao=entrada.tipo_reacao,
            gravidade=entrada.gravidade,
            descricao=entrada.descricao_reacao,
        )
        return self.repo.save(a)

    def remover_alergia(self, uuid_paciente: str, uuid_alergia: str, dados: dict, id_empresa: int):
        """ALTERADO: soft delete em vez de delete físico -- alergia é
        dado clínico de segurança (evita reintrodução acidental de uma
        substância que já causou reação), não pode simplesmente sumir
        sem rastro. Motivo obrigatório (validado via
        AlergiaRemoverSchema), mesmo padrão de DoencaCronicaService.
        As reações associadas continuam existindo fisicamente (não
        aciona o cascade de delete físico) -- só ficam invisíveis por
        tabela, já que não há listagem de reação fora do objeto
        alergia. find_by_uuid já filtra deletado, então remover de
        novo um registro já removido cai como 'não encontrado' --
        idempotente e sem vazar se já foi deletado antes ou nunca
        existiu."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        alergia = self.repo.find_by_uuid(uuid_alergia)
        if not alergia or alergia.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")

        try:
            entrada = AlergiaRemoverSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        self.repo.soft_delete(alergia, entrada.motivo_delete, entrada.observacoes_delete)
        return True

    def restaurar_alergia(self, uuid_paciente: str, uuid_alergia: str, id_empresa: int):
        """NOVO: reverte um soft delete. Mesma lógica de
        DoencaCronicaService.restaurar_doenca -- usa
        find_by_uuid_incluindo_deletados pra achar o registro mesmo
        estando deletado, e rejeita (409) restaurar um registro que
        já está ativo (não idempotente de propósito, evita mascarar
        clique duplicado/race condition)."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        alergia = self.repo.find_by_uuid_incluindo_deletados(uuid_alergia)
        if not alergia or alergia.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        if not alergia.deletado:
            raise ConflictoError(
                f"Alergia não está removida, nada a restaurar: {uuid_alergia}"
            )

        return self.repo.restaurar(alergia)

    def atualizar_alergia(self, uuid_paciente: str, uuid_alergia: str, dados: dict, id_empresa: int):
        """NOVO: atualiza codigo_substancia/flag_confirmado de uma
        alergia já registrada. substancia não é editável aqui (ver
        AlergiaAtualizarSchema); manifestacao/gravidade/reações também
        não -- isso é histórico, tratado por ReacaoAlergiaService.

        ALTERADO: usa find_by_uuid_incluindo_deletados para distinguir
        'não existe' (404) de 'existe mas está deletado' (409) --
        mesmo padrão de DoencaCronicaService.atualizar_doenca."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        alergia = self.repo.find_by_uuid_incluindo_deletados(uuid_alergia)
        if not alergia or alergia.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        if alergia.deletado:
            raise ConflictoError(
                f"Alergia removida não pode ser atualizada: {uuid_alergia}. "
                "Restaure o registro antes de editar."
            )

        try:
            entrada = AlergiaAtualizarSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        for campo, valor in entrada.campos_informados().items():
            setattr(alergia, campo, valor)

        return self.repo.save(alergia)

    
    # --- D2: Alergias mais reportadas ---
    def top_substancias(self, id_empresa: int, limite: int = 10):
        return self.repo.top_substancias(id_empresa=id_empresa, limite=limite)
 
    def gravidade_por_substancia(self, id_empresa: int, substancia: str):
        return self.repo.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)
 
    # --- F4: Gravidade geral das reações alérgicas ---
    def gravidade_geral(self, id_empresa: int):
        return self.repo.gravidade_geral(id_empresa=id_empresa)