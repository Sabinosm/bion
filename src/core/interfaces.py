"""Contratos genericos de repositorio usados por todos os dominios do Bion."""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional

T = TypeVar("T")


class IRepository(ABC, Generic[T]):
    @abstractmethod
    def find_by_id(self, id: int) -> Optional[T]: ...

    @abstractmethod
    def find_by_uuid(self, uuid: str) -> Optional[T]: ...

    @abstractmethod
    def save(self, entity: T) -> T: ...

    @abstractmethod
    def delete(self, id: int) -> bool: ...
