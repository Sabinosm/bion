"""
Regras de negócio do registro de dados clínicos durante um Atendimento:
sinais vitais, coleta clínica e input de protocolo.
"""

from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .repository import ColetaClinicaRepository, SinalVitalRepository, InputProtocoloRepository
from src.domains.atendimento.repository import AtendimentoRepository

CAMPOS_OBRIGATORIOS_SINAL_VITAL = ("tipo_parametro", "valor_numerico", "unidade")


class DadosClinicosService:
    """Casos de uso de registro de sinais vitais, coleta clínica e input de protocolo."""

    def __init__(self):
        self.atendimento_repo = AtendimentoRepository()
        self.coleta_repo = ColetaClinicaRepository()
        self.sinal_repo = SinalVitalRepository()
        self.input_repo = InputProtocoloRepository()

    def _buscar_atendimento(self, uuid_atendimento: str):
        """Busca um Atendimento pelo UUID ou lança RecursoNaoEncontradoError."""
        atendimento = self.atendimento_repo.find_by_uuid(uuid_atendimento)
        if not atendimento:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")
        return atendimento

    def registrar_sinais_vitais(self, uuid_atendimento: str, lista_sinais: list, id_usuario: int):
        """
        Registra um ou mais sinais vitais para um Atendimento.

        Args:
            uuid_atendimento: UUID do Atendimento.
            lista_sinais: lista de dicts com tipo_parametro, valor_numerico e unidade.
            id_usuario: ID de quem está coletando.

        Raises:
            RecursoNaoEncontradoError: se o Atendimento não existir.
            DadosInvalidosError: se a lista estiver vazia ou faltar campo obrigatório.
        """
        from src.models.clinico import SinalVital
        atendimento = self._buscar_atendimento(uuid_atendimento)
        if not lista_sinais:
            raise DadosInvalidosError("Informe ao menos um sinal vital.")

        registrados = []
        for s in lista_sinais:
            faltando = [c for c in CAMPOS_OBRIGATORIOS_SINAL_VITAL if s.get(c) is None]
            if faltando:
                raise DadosInvalidosError(
                    f"Campos obrigatórios ausentes em sinal vital: {', '.join(faltando)}"
                )
            sv = SinalVital(
                id_atendimento=atendimento.id,
                tipo_parametro=s["tipo_parametro"],
                valor_numerico=s["valor_numerico"],
                unidade=s["unidade"],
                sitio_medicao=s.get("sitio_medicao"),
                data_hora_medicao=datetime.now(timezone.utc),
                coletado_por=id_usuario,
                flag_validacao_faixa=s.get("flag_validacao_faixa", "dentro-do-limite"),
                flag_escala_dpoc=bool(s.get("flag_escala_dpoc", False)),
            )
            self.sinal_repo.save(sv)
            registrados.append(sv)
        return registrados

    def registrar_coleta_clinica(self, uuid_atendimento: str, dados: dict):
        """
        Cria uma ColetaClinica vinculada a um Atendimento.

        Raises:
            RecursoNaoEncontradoError: se o Atendimento não existir.
        """
        from src.models.clinico import ColetaClinica
        atendimento = self._buscar_atendimento(uuid_atendimento)
        coleta = ColetaClinica(
            id_atendimento=atendimento.id,
            desde_quando_sintomas=dados.get("desde_quando_sintomas"),
        )
        return self.coleta_repo.save(coleta)

    def registrar_input_protocolo(self, uuid_coleta: str, dados: dict):
        """
        Registra os dados de entrada (queixa, sinais, respostas de
        fluxograma) que serão usados pelo motor de protocolo
        (POST /api/ia/analisar) para gerar o resultado da triagem/consulta.

        Raises:
            RecursoNaoEncontradoError: se a ColetaClinica não existir.
        """
        from src.models.clinico import InputProtocolo

        coleta = self.coleta_repo.find_by_uuid(uuid_coleta)
        if not coleta:
            raise RecursoNaoEncontradoError(f"Coleta clínica não encontrada: {uuid_coleta}")

        ip = InputProtocolo(
            id_coleta_clinica=coleta.id,
            tipo_input=dados.get("tipo_input", "triagem"),
            input_json=dados.get("input_json"),
            queixa_principal=dados.get("queixa_principal"),
            valor_avpu=dados.get("valor_avpu"),
            dados_criticos_ausentes_json=dados.get("dados_criticos_ausentes"),
        )
        return self.input_repo.save(ip)
