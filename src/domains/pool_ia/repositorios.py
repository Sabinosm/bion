"""O que a pool espera dos repositorios (so leitura).

Sao Protocols: o repositorio real so precisa ter estes metodos. O que ja existe
no seu projeto e marcado [existe]; o resto [adicionar] no repositorio respectivo.
Todos devolvem objetos de model (que tem to_dict()) e respeitam `limite`.
"""
from __future__ import annotations

from typing import Protocol


class RepoMedicamentos(Protocol):
    # CatalogoMedicamentosRepository (todos [existe] apos a atualizacao do repository)
    def find_by_uuid(self, uuid: str): ...
    def buscar_por_principio(self, termo: str, limite: int) -> list: ...     # principio ativo, normalizado ou sinonimo
    def buscar_por_indicacao(self, termo: str, limite: int) -> list: ...     # via indicacoes_terapeuticas
    def buscar_por_classe(self, termo: str, limite: int) -> list: ...        # classe_farmaceutica
    def interacoes_entre(self, uuid: str, outros_uuids: list[str]) -> list: ...
    # devolve InteracoesMedicamentos (uuid, gravidade, medicamento_a, medicamento_b)


class RepoExames(Protocol):
    # CatalogoExamesRepository
    def find_by_uuid(self, uuid: str): ...
    def buscar_ativos(self, termo: str, tipo: str | None, limite: int) -> list: ...


class RepoExamesConteudo(Protocol):
    # CatalogoExamesConteudoRepository (usa o id interno do exame, nao o uuid)
    def contexto_para_ia(self, id_catalogo_exame: int, idioma: str, max_chars: int) -> dict | None: ...
    # {"texto","fonte","url","idioma","buscado_em"} ou None
