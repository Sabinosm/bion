"""__init__.py

Contexto clínico seguro da avaliação: a única forma de dado clínico que chega à IA.
"""
from .contexto_seguro import BlocoSeguro, ContextoSeguro, SnapshotInvalidoError

__all__ = ["BlocoSeguro", "ContextoSeguro", "SnapshotInvalidoError"]
