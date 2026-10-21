"""Contexto de uma execucao da pool. Quem monta e o SISTEMA: a IA nunca passa
empresa, paciente ou atendimento como argumento."""
from __future__ import annotations

from dataclasses import dataclass, field

from .repositorios import RepoExames, RepoMedicamentos


@dataclass(frozen=True)
class ContextoPool:
    medicamentos: RepoMedicamentos
    exames: RepoExames
    idioma: str = "pt-BR"
    id_empresa: int | None = None
    id_atendimento: int | None = None
    # uuid_catalogo dos medicamentos em uso ativos do paciente (para checar interacoes)
    uuids_em_uso: frozenset[str] = field(default_factory=frozenset)
