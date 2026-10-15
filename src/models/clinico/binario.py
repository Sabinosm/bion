"""Binário (Bloco 2) -- objeto PURO, sem tabela.

O estado da conferência mora numa coluna JSON do próprio Atendimento
(`atendimento.binario`). Este objeto lê e escreve esse JSON e concentra as
regras: o resto do código nunca mexe no dict cru.

FORMATO DO JSON (guardamos o TEXTO, não 1/0, porque são 3 estados reais):

    {"v": 1,
     "alergias":       {"estado": "nega"},
     "medicamentos":   {"estado": "preenchido"},
     "tipo_sanguineo": {"estado": "nao-coletado"},
     "doenca_cronica": {"estado": "preenchido"}}

  chave ausente   -> seção pendente (ainda não conferida neste atendimento)
  "preenchido"    -> o paciente possui o dado   (possui = True)
  "nega"          -> o paciente nega o dado     (possui = False)
  "nao-coletado"  -> não foi possível coletar   (possui = None, "não registrado")

O 1/0 / True/False / None é só uma TRADUÇÃO do texto (`possui`).

INSERT-ONLY: `registrar` recusa uma seção já conferida (ConflictoError, 409).
Não existe método para alterar ou remover uma conferência.
"""

from typing import Dict, List, Optional

from src.core.exceptions import ConflictoError

SECOES_BINARIO = ("alergias", "medicamentos", "tipo_sanguineo", "doenca_cronica")
ESTADOS = ("preenchido", "nega", "nao-coletado")
VERSAO = 1

_POSSUI = {"preenchido": True, "nega": False, "nao-coletado": None}


def estado_de(possui: Optional[bool]) -> str:
    """Tradução inversa: possui (True/False/None) -> texto do estado."""
    if possui is None:
        return "nao-coletado"
    return "preenchido" if possui else "nega"


class Binario:

    def __init__(self, estados: Optional[Dict[str, str]] = None):
        self._estados: Dict[str, str] = {}
        for secao, estado in (estados or {}).items():
            self._validar(secao, estado)
            self._estados[secao] = estado

    # ------------------------------------------------------------ construção
    @classmethod
    def de_json(cls, dados: Optional[dict]) -> "Binario":
        """Aceita None/{} (atendimento sem nenhuma seção conferida). Ignora a
        chave de versão e chaves desconhecidas; estado inválido é erro de
        integridade (o JSON só é escrito por este objeto)."""
        estados = {}
        for secao in SECOES_BINARIO:
            item = (dados or {}).get(secao)
            if item is not None:
                estados[secao] = item.get("estado")
        return cls(estados)

    @classmethod
    def de_atendimento(cls, atendimento) -> "Binario":
        return cls.de_json(getattr(atendimento, "binario", None))

    # ---------------------------------------------------------------- leitura
    def conferida(self, secao: str) -> bool:
        return secao in self._estados

    def estado(self, secao: str) -> Optional[str]:
        """Texto do estado, ou None se pendente."""
        return self._estados.get(secao)

    def possui(self, secao: str) -> Optional[bool]:
        """True=preenchido, False=nega, None=não coletado OU pendente
        (use `conferida` para distinguir)."""
        return _POSSUI.get(self._estados.get(secao))

    @property
    def pendentes(self) -> List[str]:
        return [s for s in SECOES_BINARIO if s not in self._estados]

    @property
    def completo(self) -> bool:
        return not self.pendentes

    # ----------------------------------------------------------------- escrita
    def registrar(self, secao: str, estado: str) -> None:
        """Marca a seção como conferida. Segunda vez na mesma seção = 409."""
        self._validar(secao, estado)
        if secao in self._estados:
            raise ConflictoError(f"Seção '{secao}' já conferida neste atendimento.")
        self._estados[secao] = estado

    # ------------------------------------------------------------ serialização
    def para_json(self) -> dict:
        """Dict novo a cada chamada (o SQLAlchemy só percebe a mudança da
        coluna JSON se for ATRIBUÍDO um objeto novo, não mutado)."""
        saida = {"v": VERSAO}
        for secao in SECOES_BINARIO:
            if secao in self._estados:
                saida[secao] = {"estado": self._estados[secao]}
        return saida

    def to_dict(self, secao: str) -> dict:
        """Resposta da API para uma seção JÁ conferida."""
        return {
            "secao": secao,
            "conferida": True,
            "estado": self._estados[secao],
            "possui": self.possui(secao),
        }

    @staticmethod
    def _validar(secao: str, estado) -> None:
        if secao not in SECOES_BINARIO:
            raise ValueError(f"Seção do binário inexistente: {secao}")
        if estado not in ESTADOS:
            raise ValueError(f"Estado do binário inválido para '{secao}': {estado!r}")

    def __repr__(self):
        return f"<Binario {self._estados}>"