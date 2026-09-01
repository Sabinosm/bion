from datetime import datetime, date

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ..repositories import (PacienteRepository, AlergiaRepository, ReacaoAlergiaRepository)
from src.schemas.schema_alergia import AlergiaCreateSchema, _formatar_erros_pydantic

def _parse_data(valor):
    """Aceita date/datetime já convertidos ou string ISO 'YYYY-MM-DD' vinda do JSON."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")
    
class AlergiaService:
    """Alergias, doenças crônicas e medicamentos em uso do paciente."""

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


    def remover_alergia(self, uuid_paciente: str, uuid_alergia: str, id_empresa: int):
        """Remove a alergia inteira, incluindo todo o histórico de
        reações associadas (cascade já configurado no model).

        ALTERADO: mesma checagem de posse de adicionar_reacao."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        alergia = self.repo.find_by_uuid(uuid_alergia)
        if not alergia or alergia.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        self.repo.delete_by_uuid(uuid_alergia)
        return True


    
    # --- D2: Alergias mais reportadas ---
    def top_substancias(self, id_empresa: int, limite: int = 10):
        return self.repo.top_substancias(id_empresa=id_empresa, limite=limite)
 
    def gravidade_por_substancia(self, id_empresa: int, substancia: str):
        return self.repo.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)
 
    # --- F4: Gravidade geral das reações alérgicas ---
    def gravidade_geral(self, id_empresa: int):
        return self.repo.gravidade_geral(id_empresa=id_empresa)