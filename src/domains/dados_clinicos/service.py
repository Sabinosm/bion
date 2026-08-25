"""
Regras de negócio do registro de dados clínicos durante um Atendimento:
sinais vitais, coleta clínica e input de protocolo.

ALTERADO: registrar_sinais_vitais() agora valida tipo_parametro contra
a tabela loinc_sinal_vital ANTES do insert. SinalVital.tipo_parametro
virou FK para essa tabela (05_sinal_vital_migration.sql) -- sem essa
checagem explícita, um tipo_parametro não populado na tabela de
referência estouraria um erro de FK genérico do banco em vez de uma
DadosInvalidosError clara, na hora do commit.

ColetaClinica e InputProtocolo NÃO mudaram -- são parte do domínio
Protocolo/IA, que ficou fora do escopo FHIR por decisão consciente.
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
        atendimento = self.atendimento_repo.find_by_uuid(uuid_atendimento)
        if not atendimento:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")
        return atendimento

    def _validar_tipo_parametro(self, tipo_parametro: str):
        """NOVO: confirma que o tipo_parametro existe na tabela de
        referência LOINC antes de tentar o insert -- transforma um
        possível erro de FK (genérico, difícil de interpretar pro
        cliente da API) numa DadosInvalidosError clara."""
        from src.models.clinico import LoincSinalVital
        existe = LoincSinalVital.query.filter_by(tipo_parametro=tipo_parametro).first()
        if not existe:
            raise DadosInvalidosError(
                f"tipo_parametro inválido ou não mapeado: '{tipo_parametro}'."
            )

    def registrar_sinais_vitais(self, uuid_atendimento: str, lista_sinais: list, id_usuario: int):
        """
        Registra um ou mais sinais vitais para um Atendimento.

        Raises:
            RecursoNaoEncontradoError: se o Atendimento não existir.
            DadosInvalidosError: se a lista estiver vazia, faltar campo
                obrigatório, ou tipo_parametro não for reconhecido.
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

            self._validar_tipo_parametro(s["tipo_parametro"])

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
        """SEM ALTERAÇÃO -- ColetaClinica é parte do domínio Protocolo/IA,
        fora do escopo FHIR."""
        from src.models.clinico import ColetaClinica
        atendimento = self._buscar_atendimento(uuid_atendimento)
        coleta = ColetaClinica(
            id_atendimento=atendimento.id,
            desde_quando_sintomas=dados.get("desde_quando_sintomas"),
        )
        return self.coleta_repo.save(coleta)

    def registrar_input_protocolo(self, uuid_coleta: str, dados: dict):
        """SEM ALTERAÇÃO -- InputProtocolo é parte do domínio Protocolo/IA,
        fora do escopo FHIR."""
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
    
      # --- C4: Tempo até busca por atendimento ---
    def media_horas_ate_atendimento(self, id_empresa: int, dias: int = 30):
        return self.repo.media_horas_ate_atendimento(id_empresa=id_empresa, dias=dias)