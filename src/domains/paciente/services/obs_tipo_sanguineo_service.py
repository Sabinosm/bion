

from src.core.exceptions import RecursoNaoEncontradoError
from ..repositories import (
    ObservacaoTipoSanguineoRepository,
)

    
class ObservacaoTipoSanguineoService:
    """Alergias, doenças crônicas e medicamentos em uso do paciente."""

    def __init__(self):
        self.repo = ObservacaoTipoSanguineoRepository()
     
    # --- F3: Distribuição de tipo sanguíneo na base ---
    def distribuicao_tipo_sanguineo(self, id_empresa: int):
        return self.repo.distribuicao_tipo_sanguineo(id_empresa=id_empresa)
    
    def registrar_tipo_sanguineo(self, uuid_paciente: str, valor: str, id_usuario: int):
        """NOVO exame/resultado -- cria uma observação adicional,
        preserva histórico. Este é o caminho normal de uso clínico."""
        paciente = self.buscar_por_uuid(uuid_paciente)
        paciente.registrar_tipo_sanguineo(valor, registrado_por=id_usuario)
        return self.repo.save(paciente)

    def corrigir_tipo_sanguineo(self, uuid_observacao: str, novo_valor: str):
        """CORREÇÃO de um registro específico já existente (erro de
        digitação) -- não cria histórico novo, edita o valor no lugar.
        Requer o uuid da observação específica, não do paciente."""
        obs = self.tipo_sanguineo_repo.corrigir(uuid_observacao, novo_valor)
        if not obs:
            raise RecursoNaoEncontradoError(f"Observação de tipo sanguíneo não encontrada: {uuid_observacao}")
        return obs

    def remover_tipo_sanguineo(self, uuid_observacao: str):
        """Remove um registro de observação por engano (ex: paciente
        errado, duplicata) -- diferente de corrigir_tipo_sanguineo(),
        que edita o valor mantendo o registro."""
        removido = self.tipo_sanguineo_repo.delete_by_uuid(uuid_observacao)
        if not removido:
            raise RecursoNaoEncontradoError(f"Observação de tipo sanguíneo não encontrada: {uuid_observacao}")
        return removido