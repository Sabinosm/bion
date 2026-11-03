"""repositorios.py

Contratos (Protocols) dos repositorios de leitura que a pool consome: catalogo de medicamentos, catalogo de exames e conteudo educativo de exames. O repositorio real so precisa expor estes metodos e respeitar o limite de resultados.
"""
from __future__ import annotations

from typing import Protocol


class RepoMedicamentos(Protocol):
    # implementado por CatalogoMedicamentosRepository
    def find_by_uuid(self, uuid: str): ...
    def buscar_por_principio(self, termo: str, limite: int) -> list: ...     # principio ativo, normalizado ou sinonimo
    def buscar_por_indicacao(self, termo: str, limite: int) -> list: ...     # via indicacoes_terapeuticas
    def buscar_por_classe(self, termo: str, limite: int) -> list: ...        # classe_farmaceutica
    def interacoes_entre(self, uuid: str, outros_uuids: list[str]) -> list: ...
    # devolve InteracoesMedicamentos (uuid, gravidade, medicamento_a, medicamento_b)


class RepoExames(Protocol):
    # implementado por CatalogoExamesRepository
    def find_by_uuid(self, uuid: str): ...
    def buscar_ativos(self, termo: str, tipo: str | None, limite: int) -> list: ...


class RepoExamesConteudo(Protocol):
    # implementado por CatalogoExamesConteudoRepository (usa o id interno do exame, nao o uuid)
    def contexto_para_ia(self, id_catalogo_exame: int, idioma: str, max_chars: int) -> dict | None: ...
    # {"texto","fonte","url","idioma","buscado_em"} ou None
