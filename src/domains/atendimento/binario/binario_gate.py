"""Gate do binário: "as 4 seções foram conferidas neste atendimento?".

Módulo leve DE PROPÓSITO (só o objeto Binario + exceções): quem precisa do
gate -- AtendimentoService.finalizar, ColetaClinicaService,
InputProtocoloService -- importa daqui e não do BinarioService, que puxa os
services de paciente e criaria ciclo de import.

Recebe o OBJETO Atendimento (o estado está na coluna `binario`, então não há
consulta extra ao banco).

Uso no service de coleta_clinica / input_protocolo (depois de exigir_escrita):

    from src.domains.atendimento.binario_gate import exigir_binario_completo
    exigir_binario_completo(ctx.atendimento)
"""

from typing import List

from src.core.exceptions import ConflictoError
from src.models.clinico.binario import Binario


def secoes_pendentes(atendimento) -> List[str]:
    return Binario.de_atendimento(atendimento).pendentes


def exigir_binario_completo(atendimento) -> None:
    """409 se faltar qualquer seção. 'nao-coletado' conta como conferida."""
    pendentes = secoes_pendentes(atendimento)
    if pendentes:
        raise ConflictoError(
            "Binário incompleto: confira antes as seções pendentes ("
            + ", ".join(pendentes) + ")."
        )