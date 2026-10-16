"""Checagens determinísticas da prescrição contra o catálogo de medicamentos.

Hoje cobre INTERAÇÕES medicamentosas. NÃO bloqueia nada: devolve alertas e a
cobertura da base, e quem decide é o médico. O catálogo só conhece as interações
cadastradas (a fonte atual não traz gravidade), então lista vazia nunca deve ser
apresentada como "sem interação".

Contraindicações e alergias ainda não entram aqui: Contraindicacao é um vocabulário
fechado sem ligação com o quadro do paciente, e o cruzamento depende de um mapeamento
entre as condições do paciente e esse vocabulário (a definir).
"""

from typing import Iterable, Optional

from src.domains.medicamentos.interacoes.interacoes_medicamento_repository import (
    InteracoesMedicamentosRepository,
)

AVISO_BASE_VAZIA = "Base de interações ainda vazia."
AVISO_LISTA_VAZIA = (
    "Lista vazia não significa ausência de interação clínica: "
    "a base cobre apenas as interações cadastradas."
)


class PrescricaoValidacaoService:
    def __init__(self):
        self.repo_interacoes = InteracoesMedicamentosRepository()

    def verificar_interacoes(self, ids_prescritos: Iterable[int],
                             ids_em_uso: Optional[Iterable[int]] = None) -> dict:
        """ids_prescritos: ids de CatalogoMedicamentos na prescrição.
        ids_em_uso: medicamentos que o paciente já usa; None = não consultado
        (aparece em cobertura.escopo, para a tela não sugerir uma checagem que não houve).

        Retorna {"alertas": [...], "cobertura": {...}}.
        """
        prescritos = set(ids_prescritos)
        em_uso = set(ids_em_uso or ()) - prescritos

        interacoes = self.repo_interacoes.find_cruzadas(prescritos, em_uso)
        total = self.repo_interacoes.contar()

        alertas = []
        for i in interacoes:
            entre_itens = i.id_medicamento_a in prescritos and i.id_medicamento_b in prescritos
            alertas.append({
                **i.to_dict(),
                "medicamento_a": i.medicamento_a.principio_ativo,
                "medicamento_b": i.medicamento_b.principio_ativo,
                "contexto": "entre_itens_prescritos" if entre_itens else "com_medicamento_em_uso",
            })

        escopo = ["itens_prescritos"] + (["medicamentos_em_uso"] if ids_em_uso is not None else [])
        return {
            "alertas": alertas,
            "cobertura": {
                "total_interacoes_na_base": total,
                "escopo": escopo,
                "aviso": AVISO_BASE_VAZIA if total == 0 else AVISO_LISTA_VAZIA,
            },
        }