"""Envio do input à IA: monta o snapshot e abre o registro do envio (OutputBion).

FLUXO (abrir_envio):
  1. guard de escrita (dono, em andamento, mesmo paciente, sem óbito);
  2. só triagem / avaliação médica (mesma regra do input de protocolo);
  3. binário completo (409);
  4. precisa existir um input de protocolo no atendimento (409): o vigente é
     o de maior id (insert-only);
  5. numa única transação: trava o atendimento, reconcilia o binário com os
     registros ativos (dado inserido depois pela rota granular), monta o
     InputModel e GRAVA o OutputBion com o snapshot, ainda sem resposta;
  6. a chamada à IA acontece DEPOIS, fora daqui; a resposta entra por
     `gravar_resposta`. Envio sem resposta (output_ia_json NULL) = falha ou
     em andamento, e o que foi enviado fica registrado.

O QUE É CONGELADO (OutputBion.input_ia_json): InputModel.to_dict(), isto é,
binário (nega ≠ não coletado), dados clínicos ativos, sinais vitais, coleta,
queixa, protocolos e lacunas, tudo vindo dos blocos. Não se remonta depois:
alergia muda no lugar, código dos blocos evolui, binário é reconciliado.

VIGENTE: só o último OutputBion do atendimento vale; os anteriores ficam.
"""

from src.core.exceptions import ConflictoError
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico
from src.domains.atendimento.binario.binario_gate import exigir_binario_completo
from src.domains.atendimento.binario.binario_service import BinarioService
from src.domains.atendimento.repository import AtendimentoRepository
from src.domains.input_ia.input_model import InputModel, VERSAO_INPUT_MODEL
from src.models.protocolos.output_bion import OutputBion
from .repository import InputProtocoloRepository, OutputBionRepository
from .service import TIPOS_COM_INPUT_PROTOCOLO


class EnvioIaService:

    def __init__(self):
        self._ctx = ContextoClinicoService()
        self._atendimento_repo = AtendimentoRepository()
        self._input_repo = InputProtocoloRepository()
        self._output_repo = OutputBionRepository()
        self._binario = BinarioService()

    def abrir_envio(self, uuid_atendimento: str, uuid_paciente: str,
                    autor: AutorClinico) -> OutputBion:
        """Congela o que a IA vai receber e cria o registro do envio.
        Devolve o OutputBion (id para `gravar_resposta`).

        Raises:
            RecursoNaoEncontradoError / ConflictoError / PermissaoNegadaError: do guard.
            ConflictoError: tipo de atendimento sem IA; binário incompleto;
                nenhum input de protocolo registrado.
        """
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        at = ctx.atendimento
        if at.tipo_atendimento not in TIPOS_COM_INPUT_PROTOCOLO:
            raise ConflictoError(
                "O envio à IA só existe em atendimento de triagem ou avaliação médica "
                f"(este é '{at.tipo_atendimento}')."
            )
        exigir_binario_completo(at)

        input_protocolo = self._input_repo.find_ultimo_do_atendimento(at.id)
        if input_protocolo is None:
            raise ConflictoError(
                "Registre o input de protocolo deste atendimento antes de enviar à IA."
            )

        try:
            self._atendimento_repo.travar(at)
            self._binario.reconciliar(at, autor.id_empresa)

            # O input do protocolo, a queixa e a coleta já entram pelos blocos
            # "protocolo", "queixa" e "coleta_clinica": não se injeta de novo.
            snapshot = InputModel.de_atendimento(at).to_dict()

            output = OutputBion(
                id_atendimento=at.id,
                input_ia_json=snapshot,
                versao_input_model=VERSAO_INPUT_MODEL,
            )
            self._output_repo.save(output, commit=False)
            self._output_repo.confirmar(commit=True)
            return output
        except Exception:
            self._output_repo.rollback()
            raise

    def gravar_resposta(self, output: OutputBion, output_ia_json: dict,
                        versao_modelo_ia: str = None, indice_completude=None,
                        indice_confianca=None) -> OutputBion:
        """Completa o envio com a resposta da IA. O snapshot enviado não muda."""
        try:
            output.output_ia_json = output_ia_json
            output.versao_modelo_ia = versao_modelo_ia
            output.indice_completude = indice_completude
            output.indice_confianca = indice_confianca
            self._output_repo.save(output, commit=True)
            return output
        except Exception:
            self._output_repo.rollback()
            raise
