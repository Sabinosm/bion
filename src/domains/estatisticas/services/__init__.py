"""Pacote de serviços de estatísticas do Bion.

Cada módulo cobre uma área do domínio (usuários, pacientes, consultas,
atendimentos, alergias, prescrições, exames, protocolos de IA e
interações medicamentosas). Este `__init__` reexporta todas as classes
para que `service.py` (a fachada `EstatisticasService`, um nível acima)
importe direto do pacote, sem apontar para cada arquivo individualmente.
"""

from .estatisticas_usuario import EstatisticasUsuario
from .estatisticas_paciente import EstatisticasPaciente
from .estatisticas_consulta import EstatisticasConsulta
from .estatisticas_atendimento import EstatisticasAtendimento
from .estatisticas_alergia import EstatisticasAlergia
from .estatisticas_prescricao_exame import EstatisticasPrescricaoExame
from .estatisticas_resultado_prescricao import EstatisticasResultadoPrescricao
from .estatisticas_outputbion import EstatisticasOutputBion
from .estatisticas_input_protocolo import EstatisticasInputProtocolo
from .estatisticas_interacoes_medicamentos import EstatisticasInteracoesMedicamentos
from .estatisticas_prescricao import EstatisticasPrescricao

__all__ = [
    "EstatisticasUsuario",
    "EstatisticasPaciente",
    "EstatisticasConsulta",
    "EstatisticasAtendimento",
    "EstatisticasAlergia",
    "EstatisticasPrescricaoExame",
    "EstatisticasResultadoPrescricao",
    "EstatisticasOutputBion",
    "EstatisticasInputProtocolo",
    "EstatisticasInteracoesMedicamentos",
    "EstatisticasPrescricao",
]
