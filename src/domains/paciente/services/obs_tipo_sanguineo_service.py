from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ..repositories import (
    ObservacaoTipoSanguineoRepository, PacienteRepository,
)
from src.schemas.schema_tipo_sanguineo import TipoSanguineoCreateSchema, _formatar_erros_pydantic

    
class ObservacaoTipoSanguineoService:
    """Tipo sanguíneo do paciente (histórico de observações/exames)."""

    def __init__(self):
        self.repo = ObservacaoTipoSanguineoRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        p = self.paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    # --- F3: Distribuição de tipo sanguíneo na base ---
    def distribuicao_tipo_sanguineo(self, id_empresa: int):
        return self.repo.distribuicao_tipo_sanguineo(id_empresa=id_empresa)
    
    def registrar_tipo_sanguineo(self, uuid_paciente: str, valor: str, id_usuario: int, id_empresa: int):
        """NOVO exame/resultado -- cria uma observação adicional,
        preserva histórico. Este é o caminho normal de uso clínico.

        ALTERADO: valor agora passa por TipoSanguineoCreateSchema --
        antes este era o ÚNICO domínio clínico sem NENHUMA validação,
        nem de obrigatoriedade nem de enum; um valor vazio ou fora do
        Enum (A+|A-|B+|B-|AB+|AB-|O+|O-|desconhecido) só falhava no
        commit() do save() abaixo, como erro cru do banco."""
        try:
            entrada = TipoSanguineoCreateSchema(tipo_sanguineo=valor)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        paciente = self._paciente_ou_404(uuid_paciente, id_empresa)
        paciente.registrar_tipo_sanguineo(entrada.tipo_sanguineo, registrado_por=id_usuario)
        self.paciente_repo.save(paciente)
        return paciente

    def corrigir_tipo_sanguineo(self, uuid_paciente: str, uuid_observacao: str, novo_valor: str, id_empresa: int):
        """CORREÇÃO de um registro específico já existente (erro de
        digitação) -- não cria histórico novo, edita o valor no lugar.
        Requer o uuid da observação específica, não do paciente.

        ALTERADO: novo_valor também validado via schema, mesmo
        raciocínio de registrar_tipo_sanguineo."""
        try:
            entrada = TipoSanguineoCreateSchema(tipo_sanguineo=novo_valor)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        paciente = self._paciente_ou_404(uuid_paciente, id_empresa)
        obs = self.repo.find_by_uuid(uuid_observacao)
        if not obs or obs.id_paciente != paciente.id:
            raise RecursoNaoEncontradoError(f"Observação de tipo sanguíneo não encontrada: {uuid_observacao}")
        return self.repo.corrigir(uuid_observacao, entrada.tipo_sanguineo)

    def remover_tipo_sanguineo(self, uuid_paciente: str, uuid_observacao: str, id_empresa: int):
        """Remove um registro de observação por engano (ex: paciente
        errado, duplicata) -- diferente de corrigir_tipo_sanguineo(),
        que edita o valor mantendo o registro."""
        paciente = self._paciente_ou_404(uuid_paciente, id_empresa)
        obs = self.repo.find_by_uuid(uuid_observacao)
        if not obs or obs.id_paciente != paciente.id:
            raise RecursoNaoEncontradoError(f"Observação de tipo sanguíneo não encontrada: {uuid_observacao}")
        return self.repo.delete_by_uuid(uuid_observacao)