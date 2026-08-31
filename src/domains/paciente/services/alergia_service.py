from datetime import datetime, date

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ..repositories import (PacienteRepository, AlergiaRepository, ReacaoAlergiaRepository)

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
        # ALTERADO: faltava esta linha -- remover_reacao() já chamava
        # self.reacao_repo sem ele nunca ter sido setado (AttributeError
        # certo na primeira chamada).
        self.reacao_repo = ReacaoAlergiaRepository()

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        """ALTERADO: exige id_empresa. Isolamento de tenant tem que
        acontecer aqui -- é o único ponto por onde toda operação sobre
        alergia passa antes de tocar o paciente. Sem isso, um usuário
        logado em QUALQUER empresa conseguiria ler/escrever alergia de
        paciente de OUTRA empresa, só sabendo o UUID do paciente."""
        p = self._paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def listar_alergias(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)
 
    def adicionar_alergia(self, uuid_paciente: str, dados: dict, id_empresa: int):
        """ALTERADO: Alergia não recebe mais tipo_reacao/gravidade no
        construtor -- esses campos agora criam a PRIMEIRA ReacaoAlergia
        associada, na mesma chamada (o contrato de entrada da API não
        muda: o cliente continua mandando os mesmos campos de sempre)."""
        from src.models.pacientes import Alergia
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        if not dados.get("substancia") or not dados.get("tipo_reacao") or not dados.get("gravidade"):
            raise DadosInvalidosError("substancia, tipo_reacao e gravidade são obrigatórios.")

        a = Alergia(
            id_paciente=p.id,
            substancia=dados["substancia"],
            codigo_substancia=dados.get("codigo_substancia"),
            flag_confirmado=bool(dados.get("flag_confirmado", False)),
        )
        a.registrar_reacao(
            manifestacao=dados["tipo_reacao"],
            gravidade=dados["gravidade"],
            descricao=dados.get("descricao_reacao"),
        )
        return self.repo.save(a)

    def adicionar_reacao(self, uuid_paciente: str, uuid_alergia: str, dados: dict, id_empresa: int):
        """NOVO: registra reação adicional numa alergia já existente
        (histórico de ocorrências) -- caminho que não existia antes,
        já que o schema antigo só suportava uma reação por alergia.

        ALTERADO: passou a exigir uuid_paciente + id_empresa e a
        verificar que a alergia pertence a esse paciente -- sem isso,
        alguém com acesso a QUALQUER paciente da própria empresa
        conseguiria escrever reação numa alergia de paciente de OUTRA
        empresa, só sabendo o uuid da alergia (que nunca prova posse
        sozinho)."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        alergia = self.repo.find_by_uuid(uuid_alergia)
        if not alergia or alergia.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        if not dados.get("manifestacao") or not dados.get("gravidade"):
            raise DadosInvalidosError("manifestacao e gravidade são obrigatórios.")
        alergia.registrar_reacao(
            manifestacao=dados["manifestacao"],
            gravidade=dados["gravidade"],
            descricao=dados.get("descricao"),
            data_ocorrencia=_parse_data(dados.get("data_ocorrencia")),
        )
        return self.repo.save(alergia)

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

    def remover_reacao(self, uuid_paciente: str, uuid_reacao: str, id_empresa: int):
        """Remove APENAS uma reação específica do histórico, mantendo a
        Alergia e as demais reações intactas -- uso: reação registrada
        por engano, diferente de remover a alergia toda.

        ALTERADO: usava self.reacao_repo sem ele existir (ver __init__)
        e não validava posse -- ambos corrigidos."""
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        reacao = self.reacao_repo.find_by_uuid(uuid_reacao)
        if not reacao or reacao.alergia.id_paciente != p.id:
            raise RecursoNaoEncontradoError(f"Reação não encontrada: {uuid_reacao}")
        self.reacao_repo.delete_by_uuid(uuid_reacao)
        return True

    
    # --- D2: Alergias mais reportadas ---
    def top_substancias(self, id_empresa: int, limite: int = 10):
        return self.repo.top_substancias(id_empresa=id_empresa, limite=limite)
 
    def gravidade_por_substancia(self, id_empresa: int, substancia: str):
        return self.repo.gravidade_por_substancia(id_empresa=id_empresa, substancia=substancia)
 
    # --- F4: Gravidade geral das reações alérgicas ---
    def gravidade_geral(self, id_empresa: int):
        return self.repo.gravidade_geral(id_empresa=id_empresa)