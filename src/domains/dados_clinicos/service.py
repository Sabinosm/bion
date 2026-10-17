"""
Regras de negócio do registro de dados clínicos durante um Atendimento:
sinais vitais, coleta clínica e input de protocolo.

GUARD: toda escrita (sinais vitais e coleta clínica) passa por
ContextoClinicoService.exigir_escrita: atendimento em andamento do PRÓPRIO
profissional, do mesmo paciente, enfermeiro só em triagem, paciente sem
óbito.

GATE DO BINÁRIO: a coleta clínica exige o binário completo (409). Os sinais
vitais ficam livres, sem binário.

TRANSAÇÃO: os sinais vitais de uma requisição são validados por inteiro
antes de gravar e entram num único commit (ou nada entra).

INPUT DE PROTOCOLO: mesmo guard e mesmo gate da coleta; a coleta precisa
pertencer ao atendimento da rota (senão 404). O tenant vem do guard.
"""

from datetime import datetime, timezone

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.erros_pydantic import erros_pydantic_por_campo
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico
from src.domains.atendimento.binario.binario_gate import exigir_binario_completo
from .schema import SinaisVitaisIn, ColetaClinicaIn, InputProtocoloIn
from .repository import ColetaClinicaRepository, SinalVitalRepository, InputProtocoloRepository

# O enum InputProtocolo.tipo_input só tem estes dois valores; Atendimento.tipo_atendimento
# tem mais (reavaliacao, alta, procedimento). Nesses, input de protocolo não existe.
TIPOS_COM_INPUT_PROTOCOLO = ("triagem", "avaliacao-medica")


class DadosClinicosService:
    """Casos de uso de registro de sinais vitais, coleta clínica e input de protocolo."""

    def __init__(self):
        self._ctx = ContextoClinicoService()
        self.coleta_repo = ColetaClinicaRepository()
        self.sinal_repo = SinalVitalRepository()
        self.input_repo = InputProtocoloRepository()

    @staticmethod
    def _validar(schema, dados):
        if not isinstance(dados, dict):
            raise DadosInvalidosError("Corpo da requisição inválido: esperado um objeto JSON.")
        try:
            return schema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

    # ----------------------------------------------------------- sinais vitais
    def registrar_sinais_vitais(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                                autor: AutorClinico):
        """
        Registra um ou mais sinais vitais (payload {"sinais": [...]}). Sem
        binário. Tudo ou nada: um sinal inválido derruba o lote inteiro.

        Raises:
            RecursoNaoEncontradoError / ConflictoError / PermissaoNegadaError: do guard.
            DadosInvalidosError: payload inválido ou tipo_parametro não mapeado na tabela LOINC.
        """
        from src.models.clinico import SinalVital

        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = self._validar(SinaisVitaisIn, dados)

        tipos = {s.tipo_parametro for s in entrada.sinais}
        nao_mapeados = sorted(tipos - self.sinal_repo.tipos_loinc_existentes(tipos))
        if nao_mapeados:
            raise DadosInvalidosError({
                "sinais": "tipo_parametro não mapeado na tabela LOINC: " + ", ".join(nao_mapeados)
            })

        try:
            registrados = []
            for s in entrada.sinais:
                sv = SinalVital(
                    id_atendimento=ctx.atendimento.id,
                    tipo_parametro=s.tipo_parametro,
                    valor_numerico=s.valor_numerico,
                    unidade=s.unidade,
                    sitio_medicao=s.sitio_medicao,
                    data_hora_medicao=datetime.now(timezone.utc),
                    coletado_por=autor.id_usuario,
                    flag_validacao_faixa=s.flag_validacao_faixa,
                    flag_escala_dpoc=s.flag_escala_dpoc,
                )
                self.sinal_repo.save(sv, commit=False)
                registrados.append(sv)
            self.sinal_repo.confirmar(commit=True)
            return registrados
        except Exception:
            self.sinal_repo.rollback()
            raise

    # ----------------------------------------------------------- coleta clínica
    def registrar_coleta_clinica(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                                 autor: AutorClinico):
        """
        Cria uma coleta clínica. Exige o binário completo neste atendimento (409).

        Raises:
            RecursoNaoEncontradoError / ConflictoError / PermissaoNegadaError: do guard.
            ConflictoError: binário incompleto.
            DadosInvalidosError: payload inválido.
        """
        from src.models.clinico import ColetaClinica

        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        exigir_binario_completo(ctx.atendimento)
        entrada = self._validar(ColetaClinicaIn, dados)

        coleta = ColetaClinica(
            id_atendimento=ctx.atendimento.id,
            desde_quando_sintomas=entrada.desde_quando_sintomas,
        )
        try:
            return self.coleta_repo.save(coleta)
        except Exception:
            self.coleta_repo.rollback()
            raise

    # --------------------------------------------------------- input de protocolo
    def registrar_input_protocolo(self, uuid_atendimento: str, uuid_paciente: str,
                                  uuid_coleta: str, dados: dict, autor: AutorClinico):
        """
        Registra o input de protocolo (queixa, sinais, fluxograma) de uma
        coleta clínica DESTE atendimento. Exige o binário completo (409).

        Só existe em atendimento de triagem ou avaliação médica; nos demais
        tipos (reavaliacao, alta, procedimento) = 409.
        `tipo_input`: padrão = tipo do atendimento; se vier, tem de ser igual (422).
        O conteúdo de `input_json` é livre (ainda não há schema para ele).
        InputProtocolo é parte do domínio Protocolo/IA, fora do escopo FHIR.

        Raises:
            RecursoNaoEncontradoError: atendimento/paciente do guard; coleta inexistente
                ou de outro atendimento.
            ConflictoError / PermissaoNegadaError: do guard; binário incompleto;
                tipo de atendimento sem input de protocolo.
            DadosInvalidosError: payload inválido ou tipo_input diferente do atendimento.
        """
        from src.models.clinico import InputProtocolo

        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        if ctx.atendimento.tipo_atendimento not in TIPOS_COM_INPUT_PROTOCOLO:
            raise ConflictoError(
                "Input de protocolo só existe em atendimento de triagem ou avaliação médica "
                f"(este é '{ctx.atendimento.tipo_atendimento}')."
            )
        exigir_binario_completo(ctx.atendimento)

        coleta = self.coleta_repo.find_by_uuid_do_atendimento(uuid_coleta, ctx.atendimento.id)
        if not coleta:
            raise RecursoNaoEncontradoError(
                f"Coleta clínica não encontrada neste atendimento: {uuid_coleta}"
            )

        entrada = self._validar(InputProtocoloIn, dados)
        tipo_atendimento = ctx.atendimento.tipo_atendimento
        if entrada.tipo_input is not None and entrada.tipo_input != tipo_atendimento:
            raise DadosInvalidosError({
                "tipo_input": f"deve ser igual ao tipo do atendimento ('{tipo_atendimento}')."
            })

        ip = InputProtocolo(
            id_coleta_clinica=coleta.id,
            tipo_input=tipo_atendimento,
            input_json=entrada.input_json,
            queixa_principal=entrada.queixa_principal,
            valor_avpu=entrada.valor_avpu,
            dados_criticos_ausentes_json=entrada.dados_criticos_ausentes,
        )
        try:
            return self.input_repo.save(ip)
        except Exception:
            self.input_repo.rollback()
            raise