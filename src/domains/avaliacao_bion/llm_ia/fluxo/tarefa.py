"""Tarefa = o que o worker precisa para processar uma avaliacao. So tipos simples
(serializavel em JSON), para trocar a thread por uma fila (Celery, RQ...) sem mexer no resto."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Tarefa:
    id_output: int
    uuid_output: str
    uuid_atendimento: str
    id_atendimento: int
    id_usuario: int
    id_empresa: int
    idioma: str = "pt-BR"
    uuids_em_uso: tuple[str, ...] = field(default_factory=tuple)   # medicamentos em uso com catalogo

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uuids_em_uso"] = list(self.uuids_em_uso)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Tarefa":
        return cls(**{**d, "uuids_em_uso": tuple(d.get("uuids_em_uso") or ())})
