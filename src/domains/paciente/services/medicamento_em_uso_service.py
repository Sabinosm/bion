from datetime import datetime, timezone, date

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, MedicamentoEmUsoRepository
from src.schemas.schema_medicamento_em_uso import (
    MedicamentoEmUsoCreateSchema, MedicamentoEmUsoAtualizarSchema, _formatar_erros_pydantic,
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
    """Medicamentos em uso do paciente."""

    def __init__(self):
        self.repo = MedicamentoEmUsoRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        p = self.paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p
    
    def listar_medicamentos_em_uso(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    def adicionar_medicamento_em_uso(self, uuid_paciente: str, dados: dict, id_empresa: int):
        """ALTERADO: validação de formato/obrigatórios movida para
        MedicamentoEmUsoCreateSchema (Pydantic). Adicionada também a
        checagem de que id_catalogo EXISTE em catalogo_medicamentos --
        isso é uma FK, não formato, então o Pydantic sozinho não cobre;
        sem essa query, um id_catalogo inexistente só falhava no
        commit() como IntegrityError de FK cru."""
        from src.models.pacientes import MedicamentoEmUso
        from src.models.catalogos import CatalogoMedicamentos
        p = self._paciente_ou_404(uuid_paciente, id_empresa)

        try:
            entrada = MedicamentoEmUsoCreateSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        if not CatalogoMedicamentos.query.get(entrada.id_catalogo):
            raise DadosInvalidosError(f"id_catalogo inválido: {entrada.id_catalogo} não existe no catálogo.")

        m = MedicamentoEmUso(
            id_paciente=p.id,
            id_catalogo=entrada.id_catalogo,
            descricao=entrada.descricao,
            dose=entrada.dose,
            frequencia=entrada.frequencia,
            desde=entrada.desde,
            flag_em_uso=entrada.flag_em_uso,
            status_uso=entrada.status_uso,
        )
        return self.repo.save(m)

    def atualizar_medicamento_em_uso(self, uuid_paciente: str, uuid_medicamento: str, dados: dict, id_empresa: int):
        """NOVO: atualiza um medicamento em uso já registrado -- caso
        mais comum na prática: mudar status_uso de 'ativo' para
        'interrompido' quando o tratamento termina. id_catalogo NÃO é
        editável aqui (ver MedicamentoEmUsoAtualizarSchema)."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        medicamento = self.repo.find_by_uuid(uuid_medicamento)
        if not medicamento or medicamento.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Medicamento em uso não encontrado: {uuid_medicamento}")

        try:
            entrada = MedicamentoEmUsoAtualizarSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        for campo, valor in entrada.campos_informados().items():
            setattr(medicamento, campo, valor)

        return self.repo.save(medicamento)
    
# --- F2: Pacientes em uso contínuo de medicação (%) ---
    def percentual_pacientes_em_uso_continuo(self, id_empresa: int):
        return self.repo.percentual_pacientes_em_uso_continuo(id_empresa=id_empresa)