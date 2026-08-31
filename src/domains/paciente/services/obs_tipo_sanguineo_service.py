from src.core.exceptions import RecursoNaoEncontradoError
from ..repositories import (
    ObservacaoTipoSanguineoRepository, PacienteRepository,
)

    
class ObservacaoTipoSanguineoService:
    """Tipo sanguíneo do paciente (histórico de observações/exames)."""

    def __init__(self):
        self.repo = ObservacaoTipoSanguineoRepository()
        # ALTERADO: faltava esta linha -- registrar_tipo_sanguineo
        # chamava self.buscar_por_uuid(), método que nunca existiu
        # nesta classe (é de PacienteService), e este service nem
        # tinha paciente_repo pra resolver o paciente por conta própria.
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

        ALTERADO: usa self.paciente_repo (não self.buscar_por_uuid, que
        não existia) e exige id_empresa para checar posse."""
        paciente = self._paciente_ou_404(uuid_paciente, id_empresa)
        paciente.registrar_tipo_sanguineo(valor, registrado_por=id_usuario)
        # ALTERADO: era self.repo.save(paciente) -- self.repo é
        # ObservacaoTipoSanguineoRepository, que não sabe salvar um
        # Paciente. registrar_tipo_sanguineo() do model só monta o
        # objeto ObservacaoTipoSanguineo em memória e insere na lista
        # de relacionamento; quem persiste é o PacienteRepository.
        self.paciente_repo.save(paciente)
        return paciente

    def corrigir_tipo_sanguineo(self, uuid_paciente: str, uuid_observacao: str, novo_valor: str, id_empresa: int):
        """CORREÇÃO de um registro específico já existente (erro de
        digitação) -- não cria histórico novo, edita o valor no lugar.
        Requer o uuid da observação específica, não do paciente.

        ALTERADO: usava self.tipo_sanguineo_repo, que não existia (é
        self.repo); passou a exigir uuid_paciente + id_empresa e checar
        que a observação pertence a esse paciente -- sem isso, alguém
        com acesso a qualquer paciente da própria empresa conseguiria
        corrigir observação de paciente de OUTRA empresa, só sabendo o
        uuid da observação."""
        paciente = self._paciente_ou_404(uuid_paciente, id_empresa)
        obs = self.repo.find_by_uuid(uuid_observacao)
        if not obs or obs.id_paciente != paciente.id:
            raise RecursoNaoEncontradoError(f"Observação de tipo sanguíneo não encontrada: {uuid_observacao}")
        return self.repo.corrigir(uuid_observacao, novo_valor)

    def remover_tipo_sanguineo(self, uuid_paciente: str, uuid_observacao: str, id_empresa: int):
        """Remove um registro de observação por engano (ex: paciente
        errado, duplicata) -- diferente de corrigir_tipo_sanguineo(),
        que edita o valor mantendo o registro.

        ALTERADO: mesma correção de tipo_sanguineo_repo -> repo, e
        mesma checagem de posse de corrigir_tipo_sanguineo()."""
        paciente = self._paciente_ou_404(uuid_paciente, id_empresa)
        obs = self.repo.find_by_uuid(uuid_observacao)
        if not obs or obs.id_paciente != paciente.id:
            raise RecursoNaoEncontradoError(f"Observação de tipo sanguíneo não encontrada: {uuid_observacao}")
        return self.repo.delete_by_uuid(uuid_observacao)