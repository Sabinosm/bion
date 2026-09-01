from datetime import datetime, timezone, date

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ..repositories import PacienteRepository, AlergiaRepository, ReacaoAlergiaRepository
from src.schemas.schema_alergia import ReacaoAlergiaCreateSchema, _formatar_erros_pydantic

def _parse_data(valor):
    """Aceita date/datetime já convertidos ou string ISO 'YYYY-MM-DD' vinda do JSON."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")
    
class ReacaoAlergiaService:
    """Reações alérgicas do paciente (histórico de ocorrências de uma alergia).

    ALTERADO: alinhado ao mesmo padrão dos demais services de domínio
    clínico -- id_empresa + checagem de posse (paciente -> alergia) +
    validação via schema Pydantic. Antes este service não exigia
    id_empresa nem confirmava que a alergia pertencia a um paciente da
    empresa de quem chamou (mesmo IDOR corrigido nos outros domínios);
    também não validava manifestacao/gravidade contra os Enum do banco,
    só presença.

    Nota: esta funcionalidade também existe em AlergiaService
    (adicionar_reacao/remover_reacao), já com o mesmo padrão. Os dois
    services ficam propositalmente alinhados aqui -- se um dia forem
    unificados num só, a migração é direta porque a lógica já é idêntica.
    """

    def __init__(self):
        self.repo = ReacaoAlergiaRepository()
        self._alergia_repo = AlergiaRepository()
        self._paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def adicionar_reacao(self, uuid_paciente: str, uuid_alergia: str, dados: dict, id_empresa: int):
        """NOVO: registra reação adicional numa alergia já existente
        (histórico de ocorrências).

        ALTERADO: passou a exigir uuid_paciente + id_empresa e a
        verificar que a alergia pertence a esse paciente -- sem isso,
        alguém com acesso a QUALQUER paciente da própria empresa
        conseguiria escrever reação numa alergia de paciente de OUTRA
        empresa, só sabendo o uuid da alergia."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        alergia = self._alergia_repo.find_by_uuid(uuid_alergia)
        if not alergia or alergia.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")

        try:
            entrada = ReacaoAlergiaCreateSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        alergia.registrar_reacao(
            manifestacao=entrada.manifestacao,
            gravidade=entrada.gravidade,
            descricao=entrada.descricao,
            data_ocorrencia=entrada.data_ocorrencia,
        )
        return self._alergia_repo.save(alergia)

    def remover_reacao(self, uuid_paciente: str, uuid_reacao: str, id_empresa: int):
        """Remove APENAS uma reação específica do histórico, mantendo a
        Alergia e as demais reações intactas -- uso: reação registrada
        por engano, diferente de remover a alergia toda.

        ALTERADO: passou a exigir uuid_paciente + id_empresa e checar
        que a reação pertence a esse paciente (via alergia.id_paciente)."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        reacao = self.repo.find_by_uuid(uuid_reacao)
        if not reacao or reacao.alergia.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Reação não encontrada: {uuid_reacao}")
        self.repo.delete_by_uuid(uuid_reacao)
        return True