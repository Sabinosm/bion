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
    
class DoencaCronicaService:
    """Alergias, doenças crônicas e medicamentos em uso do paciente."""

    def __init__(self):
        self.repo = DoencaCronicaRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        """ALTERADO: exige id_empresa -- ver AlergiaService para o
        raciocínio completo (mesmo padrão em todos os domínios clínicos)."""
        p = self.paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def listar_doencas(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    def adicionar_doenca(self, uuid_paciente: str, dados: dict, id_empresa: int):
        from src.models.pacientes import DoencaCronica
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
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
        return self.repo.save(d)

        # --- F1: Doenças crônicas mais comuns na base ---
    def top_cid_ativas(self, id_empresa: int, limite: int = 10):
        return self.repo.top_cid_ativas(id_empresa=id_empresa, limite=limite)