"""O que a pool espera dos repositorios (so leitura).

Sao Protocols: o repositorio real so precisa ter estes metodos. O que ja existe
no seu projeto e marcado [existe]; o resto [adicionar] no repositorio respectivo.
Todos devolvem objetos de model (que tem to_dict()) e respeitam `limite`.
"""
from __future__ import annotations

from typing import Protocol


class RepoMedicamentos(Protocol):
    def find_by_uuid(self, uuid: str): ...                                   # [confirmar]
    def buscar_por_principio(self, termo: str, limite: int) -> list: ...     # [adicionar] principio_ativo + sinonimos, normalizado
    def buscar_por_indicacao(self, termo: str, limite: int) -> list: ...     # [adicionar] via indicacoes_terapeuticas
    def buscar_por_classe(self, termo: str, limite: int) -> list: ...       # [adicionar] classe_farmaceutica
    def interacoes_entre(self, uuid: str, outros_uuids: list[str]) -> list[dict]: ...
    # [adicionar] cada item: {"uuid_a","uuid_b","gravidade","descricao"} (tabela InteracoesMedicamentos)


class RepoExames(Protocol):
    def find_by_uuid(self, uuid: str): ...                                   # [existe]
    def buscar_ativos(self, termo: str, tipo: str | None, limite: int) -> list: ...
    # [adicionar] como listar_paginado, mas sem paginacao: ativos, nome pt/en ou sinonimo
    def conteudo_por_exame(self, uuid: str, idioma: str) -> dict | None: ...
    # [adicionar] CatalogoExamesConteudo: {"titulo","fonte","texto_plano","hash_conteudo"} ou None
