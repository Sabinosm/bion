from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from ..repositories import PacienteRepository, ConsentimentoRepository

class ConsentimentoService:

    def __init__(self):
        self.repo = ConsentimentoRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        """ALTERADO: exige id_empresa -- mesmo padrão dos outros
        domínios clínicos (ver AlergiaService)."""
        p = self.paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def listar_por_paciente(self, uuid_paciente: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        return self.repo.find_por_paciente(p.id)

    def registrar(self, uuid_paciente: str, dados: dict, id_usuario_coletor: int, id_empresa: int):
        from src.models.pacientes import Consentimento
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        obrigatorios = ("versao_termo", "canal_coleta")
        faltando = [c for c in obrigatorios if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")

        ativo = self.repo.find_ativo_por_paciente(p.id)
        if ativo:
            ativo.status = "revogado"
            ativo.data_revogacao = datetime.now(timezone.utc)
            ativo.motivo_revogacao = "Substituído por novo termo de consentimento."
            self.repo.save(ativo)

        c = Consentimento(
            id_paciente=p.id,
            coletado_por=id_usuario_coletor,
            versao_termo=dados["versao_termo"],
            data_consentimento=datetime.now(timezone.utc),
            canal_coleta=dados["canal_coleta"],
            escopo_consentimento_json=dados.get("escopo_consentimento"),
            hash_documento=dados.get("hash_documento"),
        )
        return self.repo.save(c)

    def revogar(self, uuid_paciente: str, motivo: str, id_empresa: int):
        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        ativo = self.repo.find_ativo_por_paciente(p.id)
        if not ativo:
            raise RecursoNaoEncontradoError("Não há consentimento ativo para este paciente.")
        ativo.status = "revogado"
        ativo.data_revogacao = datetime.now(timezone.utc)
        ativo.motivo_revogacao = motivo or "Revogado a pedido do titular."
        return self.repo.save(ativo)