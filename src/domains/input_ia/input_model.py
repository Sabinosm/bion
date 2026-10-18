"""InputModel: a caixa grande. So compoe as caixas pequenas (blocos)."""
from __future__ import annotations

from typing import Callable, Iterable

from .config import Config
from .nucleo import Bloco
from .registro import Fabrica, fabricas

# Versão do FORMATO do snapshot (blocos/chaves). Suba ao mudar a estrutura de
# um bloco; vai para OutputBion.versao_input_model para ler snapshots antigos.
VERSAO_INPUT_MODEL = 1


class InputModel:
    def __init__(self, blocos: list[Bloco], config: Config | None = None,
                 meta: dict[str, Fabrica] | None = None):
        self._blocos = {b.nome: b for b in blocos}
        self.config = config or Config()
        self._meta = meta or {}

    @classmethod
    def de_atendimento(cls, atendimento, config: Config | None = None) -> "InputModel":
        fabs = fabricas()
        blocos = []
        for f in fabs:
            b = f.fn(atendimento)
            if b.nome != f.nome:
                raise ValueError(f"fabrica '{f.nome}' devolveu bloco '{b.nome}'")
            blocos.append(b)
        return cls(blocos, config, {f.nome: f for f in fabs})

    @property
    def idioma(self) -> str:
        return self.config.idioma

    # ------------------------------------------------------------- acesso
    def nomes(self) -> list[str]:
        return list(self._blocos)

    def bloco(self, nome: str) -> Bloco:
        return self._blocos[nome]              # input.bloco("alergias").to_dict()

    def _selecionar(self, nomes: Iterable[str] | None) -> list[Bloco]:
        if nomes is None:
            return list(self._blocos.values())
        return [self._blocos[n] for n in nomes]

    def contexto_total(self) -> dict:
        return {n: b.to_dict() for n, b in self._blocos.items()}

    def contexto_por_grupo(self) -> dict[str, dict]:
        saida: dict[str, dict] = {}
        for n, b in self._blocos.items():
            grupo = self._meta[n].grupo if n in self._meta else "outros"
            saida.setdefault(grupo, {})[n] = b.to_dict()
        return saida

    # ----------------------------------------------------- piscina de metodos
    def metodos(self) -> dict[str, Callable[[], dict]]:
        """Um metodo sem argumentos por bloco, nome -> dados. E o que uma
        camada de IA pode expor como ferramentas, uma por caixa pequena."""
        return {n: (lambda b=b: b.to_dict()) for n, b in self._blocos.items()}

    def catalogo(self) -> list[dict]:
        """Nome, grupo e descricao de cada metodo da piscina."""
        saida = []
        for n in self._blocos:
            m = self._meta.get(n)
            saida.append({"nome": n,
                          "grupo": m.grupo if m else None,
                          "descricao": m.descricao if m else None})
        return saida

    # ------------------------------------------------------------ diagnostico
    def campos_faltando(self, nomes: Iterable[str] | None = None) -> list[str]:
        return [x for b in self._selecionar(nomes) for x in b.faltando()]

    def inconsistencias(self) -> list[str]:
        return [n for n, b in self._blocos.items() if b.inconsistente]

    # ----------------------------------------------------------- serializacao
    def to_dict(self) -> dict:
        return {"idioma_resposta": self.idioma,
                "faltando": self.campos_faltando(),
                "contexto": self.contexto_total()}

    def to_prompt(self, nomes: Iterable[str] | None = None) -> str:
        blocos = self._selecionar(nomes)
        partes = [f"idioma_resposta: {self.idioma}"]
        falt = [x for b in blocos for x in b.faltando()]
        if falt:
            partes.append("## lacunas\n" + "\n".join(f"- {x}" for x in falt))
        partes += [b.to_prompt() for b in blocos]
        return "\n\n".join(partes)
