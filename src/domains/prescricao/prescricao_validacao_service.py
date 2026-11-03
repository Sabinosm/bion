"""prescricao_validacao_service.py

Checagens determinísticas da prescrição contra o catálogo de medicamentos.

Hoje cobre INTERAÇÕES medicamentosas, entre os itens prescritos e entre estes e os
medicamentos que o paciente já usa (registros ativos). NÃO bloqueia nada: devolve
alertas e a cobertura da base, e quem decide é o médico. O catálogo só conhece as interações
cadastradas (a fonte atual não traz gravidade), então lista vazia nunca deve ser
apresentada como "sem interação".

Contraindicações e alergias ainda não entram aqui: Contraindicacao é um vocabulário
fechado sem ligação com o quadro do paciente, e o cruzamento depende de um mapeamento
entre as condições do paciente e esse vocabulário (a definir).
"""

from typing import Iterable, Optional, Set

from src.core.exceptions import RecursoNaoEncontradoError
from src.domains.paciente.services.medicamento_em_uso_service import MedicamentoEmUsoService
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
        self.medicamento_em_uso_svc = MedicamentoEmUsoService()

    def ids_em_uso(self, resultado, id_empresa: int) -> Set[int]:
        """Ids de CatalogoMedicamentos dos medicamentos ATIVOS que o paciente do atendimento já usa.

        Conjunto vazio quando o paciente não usa nenhum (a consulta foi feita, só não achou nada);
        é isso que faz a cobertura declarar o escopo `medicamentos_em_uso`.
        """
        uuid_paciente = resultado.atendimento.consulta.paciente.uuid
        try:
            em_uso = self.medicamento_em_uso_svc.listar_medicamentos_em_uso(
                uuid_paciente, id_empresa, apenas_ativos=True
            )
        except RecursoNaoEncontradoError:
            return set()
        return {m.catalogo_medicamentos.id for m in em_uso if m.catalogo_medicamentos}

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
