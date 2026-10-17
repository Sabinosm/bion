"""Bloco 'paciente': sexo, idade, peso e altura."""
from __future__ import annotations

from datetime import date

from ..nucleo import Bloco, idade, limpar, num
from ..registro import bloco

NOME = "paciente"
_SEXO = {"M": "masculino", "F": "feminino", "I": "indeterminado"}


def _ref(at) -> date:
    return at.data_hora_inicio.date() if at.data_hora_inicio else date.today()


@bloco(NOME, ordem=10, descricao="Sexo, idade, peso e altura do paciente.")
def montar(at) -> Bloco:
    p = at.consulta.paciente
    anos, meses = idade(p.data_nascimento, _ref(at))
    peso = num(getattr(p, "peso", None))      # assumido: kg
    altura = num(getattr(p, "altura", None))  # assumido: cm
    dados = limpar({
        "sexo": _SEXO.get(p.sexo_biologico),
        "idade_anos": anos,
        "idade_meses": meses if anos is not None and anos < 2 else None,
        "peso_kg": peso,
        "altura_cm": altura,
    })
    lacunas = tuple(
        f"paciente: {campo}" for campo, ausente in (
            ("idade (sem data de nascimento)", anos is None),
            ("peso", peso is None),
            ("altura", altura is None),
        ) if ausente
    )
    return Bloco(NOME, dados, lacunas)
