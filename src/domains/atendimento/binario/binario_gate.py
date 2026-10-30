"""binario_gate.py

Gate do binário: responde se as quatro seções foram conferidas neste
atendimento.

O módulo é leve DE PROPÓSITO (só o objeto Binario e a exceção de conflito).
Quem precisa do gate (finalização do atendimento, coleta clínica, input de
protocolo e envio à IA) importa daqui e não do serviço do binário, que puxa os
services de paciente e criaria ciclo de import. Recebe o OBJETO Atendimento: o
estado vive na coluna `binario`, então não há consulta extra ao banco.

Uso, depois da checagem de escrita:

    from src.domains.atendimento.binario.binario_gate import exigir_binario_completo
    exigir_binario_completo(ctx.atendimento)
"""

from typing import List

from src.core.exceptions import ConflictoError
from src.models.clinico.binario import Binario


def secoes_pendentes(atendimento) -> List[str]:
    """Seções ainda não conferidas neste atendimento."""
    return Binario.de_atendimento(atendimento).pendentes


def exigir_binario_completo(atendimento) -> None:
    """Exige que todas as seções estejam conferidas. 'nao-coletado' conta como conferida.

    Raises:
        ConflictoError: se faltar qualquer seção (409).
    """
    pendentes = secoes_pendentes(atendimento)
    if pendentes:
        raise ConflictoError(
            "Binário incompleto: confira antes as seções pendentes ("
            + ", ".join(pendentes) + ")."
        )
