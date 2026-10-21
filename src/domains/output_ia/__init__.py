"""Output da IA: a casca que ela preenche (schema = proposta existente + extras),
a validacao da resposta, o que o sistema acrescenta (envelope, requisicoes) e
o que vai ao front (output_front)."""
from .envelope import colunas_envio, colunas_resposta
from .output_front import montar_output_front
from .requisicoes import RequisicaoIA, colunas_requisicoes
from .schema import JustificativaMedicamento, OutputIA, PerguntaPendente, casca
from .validacao import (BLOCOS_OBRIGATORIOS_PARA_MEDICAMENTO, Interpretacao, interpretar,
                        validar_contra_input)

__all__ = ["BLOCOS_OBRIGATORIOS_PARA_MEDICAMENTO", "Interpretacao", "JustificativaMedicamento", "OutputIA",
           "PerguntaPendente", "RequisicaoIA", "casca", "colunas_envio", "colunas_requisicoes",
           "colunas_resposta", "interpretar", "montar_output_front", "validar_contra_input"]
