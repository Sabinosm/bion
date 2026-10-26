"""Este arquivo define o resultado do caso de uso e sua projeção para a resposta HTTP, que mantém o formato de OutputBion.to_dict()."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ...domain.schemas.responses import RespostaLLM

MENSAGEM_FALLBACK = (
    "A análise por IA está indisponível no momento. Os protocolos determinísticos e o registro clínico não foram afetados."
)


@dataclass(frozen=True)
class LLMAnalysisResult:
    llm_disponivel: bool
    persistido: bool
    tipo_analise: str
    versao_prompt: str
    versao_modelo_ia: str
    simulado: bool
    resposta: Optional[RespostaLLM] = None
    categoria_falha: Optional[str] = None
    uuid_output: Optional[str] = None
    versao_input_model: Optional[int] = None
    criado_em: Optional[str] = None
    indice_completude: Optional[float] = None
    indice_confianca: Optional[float] = None

    def output_ia(self) -> Dict[str, Any]:
        """Esta função devolve o conteúdo de output_ia: a resposta validada mais metadados, ou o payload de fallback."""
        if self.llm_disponivel and self.resposta is not None:
            return {
                **self.resposta.para_dict_persistencia(),
                "llm_disponivel": True,
                "simulado": self.simulado,
                "tipo_analise": self.tipo_analise,
                "versao_prompt": self.versao_prompt,
            }
        return {
            "llm_disponivel": False,
            "motivo": self.categoria_falha,
            "mensagem": MENSAGEM_FALLBACK,
            "tipo_analise": self.tipo_analise,
            "versao_prompt": self.versao_prompt,
        }

    def para_resposta_http(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid_output,
            "versao_input_model": self.versao_input_model,
            "output_ia": self.output_ia(),
            "versao_modelo_ia": self.versao_modelo_ia,
            "indice_completude": self.indice_completude,
            "indice_confianca": self.indice_confianca,
            "criado_em": self.criado_em,
            "persistido": self.persistido,
        }
