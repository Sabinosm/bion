
from datetime import datetime, timezone, date

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt, hmac_sha256
from ..repositories import (
    PacienteRepository, AlergiaRepository, ReacaoAlergiaRepository,
    DoencaCronicaRepository, MedicamentoEmUsoRepository, ConsentimentoRepository,
    ObservacaoTipoSanguineoRepository,
)

def _parse_data(valor):
    """Aceita date/datetime já convertidos ou string ISO 'YYYY-MM-DD' vinda do JSON."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")
    
class DadosClinicosService:
    """Alergias, doenças crônicas e medicamentos em uso do paciente."""

    def __init__(self):
        self.alergia_repo = AlergiaRepository()
        self.reacao_repo = ReacaoAlergiaRepository()
        self.doenca_repo = DoencaCronicaRepository()
        self.medicamento_repo = MedicamentoEmUsoRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str):
        p = self.paciente_repo.find_by_uuid(uuid_paciente)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def listar_alergias(self, uuid_paciente: str):
        p = self._paciente_ou_404(uuid_paciente)
        return self.alergia_repo.find_por_paciente(p.id)

    def adicionar_alergia(self, uuid_paciente: str, dados: dict):
        """ALTERADO: Alergia não recebe mais tipo_reacao/gravidade no
        construtor -- esses campos agora criam a PRIMEIRA ReacaoAlergia
        associada, na mesma chamada (o contrato de entrada da API não
        muda: o cliente continua mandando os mesmos campos de sempre)."""
        from src.models.pacientes import Alergia
        p = self._paciente_ou_404(uuid_paciente)
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
        return self.alergia_repo.save(a)

    def adicionar_reacao(self, uuid_alergia: str, dados: dict):
        """NOVO: registra reação adicional numa alergia já existente
        (histórico de ocorrências) -- caminho que não existia antes,
        já que o schema antigo só suportava uma reação por alergia."""
        alergia = self.alergia_repo.find_by_uuid(uuid_alergia)
        if not alergia:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        if not dados.get("manifestacao") or not dados.get("gravidade"):
            raise DadosInvalidosError("manifestacao e gravidade são obrigatórios.")
        alergia.registrar_reacao(
            manifestacao=dados["manifestacao"],
            gravidade=dados["gravidade"],
            descricao=dados.get("descricao"),
            data_ocorrencia=_parse_data(dados.get("data_ocorrencia")),
        )
        return self.alergia_repo.save(alergia)

    def remover_alergia(self, uuid_alergia: str):
        """Remove a alergia inteira, incluindo todo o histórico de
        reações associadas (cascade já configurado no model)."""
        removido = self.alergia_repo.delete_by_uuid(uuid_alergia)
        if not removido:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        return removido

    def remover_reacao(self, uuid_reacao: str):
        """Remove APENAS uma reação específica do histórico, mantendo a
        Alergia e as demais reações intactas -- uso: reação registrada
        por engano, diferente de remover a alergia toda."""
        removido = self.reacao_repo.delete_by_uuid(uuid_reacao)
        if not removido:
            raise RecursoNaoEncontradoError(f"Reação não encontrada: {uuid_reacao}")
        return removido

    def listar_doencas(self, uuid_paciente: str):
        p = self._paciente_ou_404(uuid_paciente)
        return self.doenca_repo.find_por_paciente(p.id)

    def adicionar_doenca(self, uuid_paciente: str, dados: dict):
        from src.models.pacientes import DoencaCronica
        p = self._paciente_ou_404(uuid_paciente)
        obrigatorios = ("codigo_cid10", "descricao_cid10", "desde", "status")
        faltando = [c for c in obrigatorios if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")
        d = DoencaCronica(
            id_paciente=p.id,
            codigo_cid10=dados["codigo_cid10"],
            descricao_cid10=dados["descricao_cid10"],
            desde=_parse_data(dados["desde"]),
            status=dados["status"],
            observacoes=dados.get("observacoes"),
        )
        return self.doenca_repo.save(d)

    def listar_medicamentos_em_uso(self, uuid_paciente: str):
        p = self._paciente_ou_404(uuid_paciente)
        return self.medicamento_repo.find_por_paciente(p.id)

    def adicionar_medicamento_em_uso(self, uuid_paciente: str, dados: dict):
        from src.models.pacientes import MedicamentoEmUso
        p = self._paciente_ou_404(uuid_paciente)
        m = MedicamentoEmUso(
            id_paciente=p.id,
            id_catalogo=dados.get("id_catalogo"),
            descricao=dados.get("descricao"),
            dose=dados.get("dose"),
            frequencia=dados.get("frequencia"),
            desde=_parse_data(dados.get("desde")),
            flag_em_uso=bool(dados.get("flag_em_uso", True)),
            status_uso=dados.get("status_uso", "ativo" if dados.get("flag_em_uso", True) else "interrompido"),
        )
        return self.medicamento_repo.save(m)