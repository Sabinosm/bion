"""Este arquivo carrega prompts versionados de templates/<tipo>/<versao>.md e os separa em regras do sistema e mensagem de dados.

Formato do arquivo: a marca <!-- SISTEMA --> abre as regras e a marca <!-- DADOS --> abre a mensagem
do usuário, que contém uma única vez o marcador {contexto_json}.
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Dict, List, Tuple

from ...domain.ports.prompt_source import PromptMontado
from ..llm.exceptions import PromptNaoEncontradoError

logger = logging.getLogger("bion.ia.prompts")

DIRETORIO_PADRAO = Path(__file__).parent / "templates"
MARCA_SISTEMA = "<!-- SISTEMA -->"
MARCA_DADOS = "<!-- DADOS -->"
MARCADOR_CONTEXTO = "{contexto_json}"
_TIPO_VALIDO = re.compile(r"^[a-z][a-z_]{0,49}$")
_VERSAO_VALIDA = re.compile(r"^v\d{1,3}$")
_MARCADOR_QUALQUER = re.compile(r"\{[a-z_]+\}")


class PromptService:
    def __init__(self, diretorio: Path = DIRETORIO_PADRAO):
        self._dir = Path(diretorio)
        self._cache: Dict[Tuple[str, str], Tuple[str, str]] = {}
        self._lock = threading.Lock()

    def _carregar(self, tipo: str, versao: str) -> Tuple[str, str]:
        if not _TIPO_VALIDO.match(tipo or "") or not _VERSAO_VALIDA.match(versao or ""):
            raise PromptNaoEncontradoError("identificador_invalido")
        chave = (tipo, versao)
        with self._lock:
            if chave in self._cache:
                return self._cache[chave]
        caminho = self._dir / tipo / f"{versao}.md"
        try:
            bruto = caminho.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.error("prompt_indisponivel", extra={"tipo_analise": tipo, "versao_prompt": versao})
            raise PromptNaoEncontradoError("arquivo_ausente_ou_ilegivel") from None
        partes = self._separar(bruto)
        with self._lock:
            self._cache[chave] = partes
        return partes

    @staticmethod
    def _separar(bruto: str) -> Tuple[str, str]:
        if MARCA_SISTEMA not in bruto or MARCA_DADOS not in bruto:
            raise PromptNaoEncontradoError("marcas_ausentes")
        antes, _, depois = bruto.partition(MARCA_DADOS)
        sistema = antes.replace(MARCA_SISTEMA, "", 1).strip()
        usuario = depois.strip()
        if not sistema or MARCADOR_CONTEXTO in sistema or usuario.count(MARCADOR_CONTEXTO) != 1:
            raise PromptNaoEncontradoError("estrutura_invalida")
        return sistema, usuario

    def montar(self, tipo_analise: str, versao: str, contexto_json: str) -> PromptMontado:
        """Esta função devolve o prompt com o contexto injetado por substituição literal, sem interpretar chaves do conteúdo."""
        sistema, usuario = self._carregar(tipo_analise, versao)
        return PromptMontado(sistema=sistema, usuario=usuario.replace(MARCADOR_CONTEXTO, contexto_json))

    def listar_versoes(self, tipo_analise: str) -> List[str]:
        if not _TIPO_VALIDO.match(tipo_analise or ""):
            return []
        pasta = self._dir / tipo_analise
        return sorted(p.stem for p in pasta.glob("*.md")) if pasta.is_dir() else []

    def marcadores_nao_permitidos(self, tipo: str, versao: str) -> List[str]:
        """Esta função lista marcadores {nome} do template além de {contexto_json}. Serve de verificação de integridade."""
        sistema, usuario = self._carregar(tipo, versao)
        encontrados = set(_MARCADOR_QUALQUER.findall(sistema + usuario))
        return sorted(encontrados - {MARCADOR_CONTEXTO})
