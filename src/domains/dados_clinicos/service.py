"""
Regras de negócio do registro de dados clínicos durante um Atendimento:
sinais vitais, coleta clínica e input de protocolo.

ALTERADO (Bloco 2) -- sinais vitais e coleta clínica:

  GUARD: toda escrita passa por ContextoClinicoService.exigir_escrita
  (atendimento em andamento do PRÓPRIO profissional, mesmo paciente, enfermeiro
  só em triagem, paciente sem óbito, tenant). O autor vem da sessão.

  GATE: a coleta clínica exige o binário completo (409). Sinais vitais ficam
  LIVRES (não chamam o gate).

  TRANSAÇÃO: `commit=True` (padrão) grava tudo ou nada. `commit=False` só faz
  flush: quem chama é o dono da transação (não há commit nem rollback aqui).
  Sinais vitais: TODOS os itens são validados antes de criar qualquer um, e
  gravam num único commit (antes, cada item comitava sozinho e uma falha no
  meio deixava gravação parcial).

  VALIDAÇÃO (422): enums (unidade, sítio, flag) vêm das colunas do model, e
  tipo_parametro precisa estar nos enums E na tabela loinc_sinal_vital
  (05_sinal_vital_migration.sql). Erros por item: {"sinais[0].unidade": "..."}.

registrar_input_protocolo NÃO mudou (próximo passo): continua no formato
antigo, sem guard, e é o domínio Protocolo/IA, fora do escopo FHIR.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico
from src.domains.atendimento.binario.binario_gate import exigir_binario_completo
from .repository import ColetaClinicaRepository, SinalVitalRepository, InputProtocoloRepository

CAMPOS_OBRIGATORIOS_SINAL_VITAL = ("tipo_parametro", "valor_numerico", "unidade")
MAX_SINAIS_POR_REQUISICAO = 50
MAX_HORAS_SINTOMAS = 32767  # SMALLINT
_LIMITE_VALOR = Decimal(10) ** 8  # Numeric(10, 2)


def _enums(coluna) -> tuple:
    return tuple(coluna.type.enums)


class DadosClinicosService:
    """Casos de uso de registro de sinais vitais, coleta clínica e input de protocolo."""

    def __init__(self):
        self._ctx = ContextoClinicoService()
        self.coleta_repo = ColetaClinicaRepository()
        self.sinal_repo = SinalVitalRepository()
        self.input_repo = InputProtocoloRepository()

    # ---------------------------------------------------------- sinais vitais
    @staticmethod
    def _tipos_loinc() -> set:
        """Tipos mapeados na tabela de referência LOINC (tabela pequena)."""
        from src.models.clinico import LoincSinalVital
        return {r.tipo_parametro for r in LoincSinalVital.query.all()}

    @staticmethod
    def _numero(v):
        """Decimal finito dentro de Numeric(10,2), ou None. Aceita número ou
        string numérica; recusa bool, NaN, infinito e fora de faixa."""
        if isinstance(v, bool):
            return None
        try:
            d = Decimal(str(v).strip())
        except (InvalidOperation, ValueError):
            return None
        if not d.is_finite() or abs(d) >= _LIMITE_VALOR:
            return None
        return d

    def _validar_sinal(self, i: int, s, enums: dict, tipos_loinc: set):
        """Devolve (erros, valores_normalizados) de UM item da lista."""
        pref = f"sinais[{i}]"
        if not isinstance(s, dict):
            return {pref: "esperado um objeto."}, None

        erros = {}
        for c in CAMPOS_OBRIGATORIOS_SINAL_VITAL:
            if s.get(c) is None:
                erros[f"{pref}.{c}"] = "obrigatório."

        tipo = s.get("tipo_parametro")
        if tipo is not None and not (
            isinstance(tipo, str) and tipo in enums["tipo_parametro"] and tipo in tipos_loinc
        ):
            erros[f"{pref}.tipo_parametro"] = f"inválido ou não mapeado: {tipo!r}."

        valor = None
        if s.get("valor_numerico") is not None:
            valor = self._numero(s["valor_numerico"])
            if valor is None:
                erros[f"{pref}.valor_numerico"] = "deve ser um número finito."

        for campo in ("unidade", "sitio_medicao", "flag_validacao_faixa"):
            v = s.get(campo)
            if v is not None and (not isinstance(v, str) or v not in enums[campo]):
                erros[f"{pref}.{campo}"] = "valor inválido; use um de: " + ", ".join(enums[campo])

        escala = s.get("flag_escala_dpoc", False)
        if not isinstance(escala, bool):
            erros[f"{pref}.flag_escala_dpoc"] = "deve ser true ou false."

        if erros:
            return erros, None
        return None, {
            "tipo_parametro": tipo,
            "valor_numerico": valor,
            "unidade": s["unidade"],
            "sitio_medicao": s.get("sitio_medicao"),
            "flag_validacao_faixa": s.get("flag_validacao_faixa") or "dentro-do-limite",
            "flag_escala_dpoc": escala,
        }

    def registrar_sinais_vitais(self, uuid_atendimento: str, uuid_paciente: str, lista_sinais,
                                autor: AutorClinico, commit: bool = True):
        """
        Registra um ou mais sinais vitais num Atendimento (tudo ou nada).
        NÃO exige o binário: sinais vitais são livres.

        Raises:
            RecursoNaoEncontradoError / ConflictoError / PermissaoNegadaError:
                vindos do guard (ver ContextoClinicoService.exigir_escrita).
            DadosInvalidosError: lista vazia/grande demais, item não-objeto,
                campo obrigatório ausente, enum ou número inválido,
                tipo_parametro desconhecido. Nada é gravado.
        """
        from src.models.clinico import SinalVital

        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)

        if not isinstance(lista_sinais, list) or not lista_sinais:
            raise DadosInvalidosError("Informe ao menos um sinal vital em 'sinais' (lista).")
        if len(lista_sinais) > MAX_SINAIS_POR_REQUISICAO:
            raise DadosInvalidosError(
                f"No máximo {MAX_SINAIS_POR_REQUISICAO} sinais vitais por requisição."
            )

        enums = {
            "tipo_parametro": _enums(SinalVital.tipo_parametro),
            "unidade": _enums(SinalVital.unidade),
            "sitio_medicao": _enums(SinalVital.sitio_medicao),
            "flag_validacao_faixa": _enums(SinalVital.flag_validacao_faixa),
        }
        tipos_loinc = self._tipos_loinc()

        erros, validos = {}, []
        for i, s in enumerate(lista_sinais):
            e, v = self._validar_sinal(i, s, enums, tipos_loinc)
            if e:
                erros.update(e)
            else:
                validos.append(v)
        if erros:
            raise DadosInvalidosError(erros)

        agora = datetime.now(timezone.utc)
        try:
            registrados = []
            for v in validos:
                sv = SinalVital(
                    id_atendimento=ctx.atendimento.id,
                    data_hora_medicao=agora,
                    coletado_por=autor.id_usuario,
                    **v,
                )
                self.sinal_repo.save(sv, commit=False)
                registrados.append(sv)
            self.sinal_repo.confirmar(commit)
            return registrados
        except Exception:
            if commit:
                self.sinal_repo.rollback()
            raise

    # --------------------------------------------------------- coleta clínica
    def registrar_coleta_clinica(self, uuid_atendimento: str, uuid_paciente: str, dados,
                                 autor: AutorClinico, commit: bool = True):
        """
        Cria uma coleta clínica no Atendimento. Exige o BINÁRIO COMPLETO (409).

        Raises:
            RecursoNaoEncontradoError / ConflictoError / PermissaoNegadaError:
                vindos do guard; ConflictoError também se o binário estiver incompleto.
            DadosInvalidosError: corpo não-objeto ou desde_quando_sintomas
                inválido (inteiro de horas, 0..32767, opcional).
        """
        from src.models.clinico import ColetaClinica

        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        exigir_binario_completo(ctx.atendimento)

        if not isinstance(dados, dict):
            raise DadosInvalidosError("Corpo da requisição inválido: esperado um objeto JSON.")
        horas = dados.get("desde_quando_sintomas")
        if horas is not None and (
            isinstance(horas, bool) or not isinstance(horas, int) or not 0 <= horas <= MAX_HORAS_SINTOMAS
        ):
            raise DadosInvalidosError({
                "desde_quando_sintomas": f"deve ser um inteiro de horas entre 0 e {MAX_HORAS_SINTOMAS}."
            })

        try:
            coleta = ColetaClinica(id_atendimento=ctx.atendimento.id, desde_quando_sintomas=horas)
            return self.coleta_repo.save(coleta, commit=commit)
        except Exception:
            if commit:
                self.coleta_repo.rollback()
            raise

    # -------------------------------------------------------- input protocolo
    def registrar_input_protocolo(self, uuid_coleta: str, dados: dict):
        """SEM ALTERAÇÃO (próximo passo) -- InputProtocolo é parte do domínio
        Protocolo/IA, fora do escopo FHIR."""
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