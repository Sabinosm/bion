from typing import Optional, List

from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from src.models import db
from src.core.interfaces import IRepository
from src.models.catalogos.interacoes_medicamentos import InteracoesMedicamentos
# AJUSTE o caminho se o model estiver em outro modulo
from src.models.catalogos.catalogo_medicamentos import CatalogoMedicamentos

class InteracoesMedicamentosRepository(IRepository[InteracoesMedicamentos]):

    def find_by_id(self, id: int) -> Optional[InteracoesMedicamentos]:
        return db.session.get(InteracoesMedicamentos, id)

    def find_by_uuid(self, uuid: str) -> Optional[InteracoesMedicamentos]:
        return InteracoesMedicamentos.query.filter_by(uuid=uuid).first()

    def find_por_par_ordenado(self, id_a: int, id_b: int) -> Optional[InteracoesMedicamentos]:
        """Busca exata pelo par (id_a, id_b) já ordenado -- id_a deve
        ser sempre o menor dos dois. Quem chama é responsável por
        ordenar antes (ver AtualizacaoInteracoesService), garantindo em
        código a mesma regra que o UniqueConstraint do banco espera."""
        return InteracoesMedicamentos.query.filter_by(
            id_medicamento_a=id_a, id_medicamento_b=id_b
        ).first()

    def contar(self) -> int:
        """Total de interações cadastradas (usado para informar a
        cobertura da base ao consultar interações de um medicamento)."""
        return InteracoesMedicamentos.query.count()

    def add(self, entity: InteracoesMedicamentos) -> InteracoesMedicamentos:
        """Adiciona/atualiza sem commit (só flush): quem chama controla a
        transação -- usado pela sincronização em lote."""
        db.session.add(entity)
        db.session.flush()
        return entity

    def save(self, entity: InteracoesMedicamentos) -> InteracoesMedicamentos:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[InteracoesMedicamentos]:
        return InteracoesMedicamentos.query.all()

    # --- D1: Interações medicamentosas cadastradas por gravidade ---
    def contar_por_gravidade(self) -> dict:
        """Contagem de interações cadastradas no catálogo, por
        gravidade. Não filtra por empresa nem cruza com pacientes reais
        -- é dado de catálogo/base de conhecimento, igual pra todas as
        empresas (equivalente a uma tabela de referência médica).

        `gravidade` é String(50) livre no schema (não Enum), então
        normaliza para minúsculo/sem espaços nas pontas antes de
        agrupar -- evita fragmentar o resultado por inconsistência de
        cadastro (ex: "Grave" e "grave " contando como categorias
        diferentes). Isso reduz o risco, mas não resolve de vez: se o
        cadastro usar sinônimos distintos ("grave" vs "alta"), ainda
        aparecem como grupos separados -- resolve de verdade só
        convertendo a coluna para Enum no schema.

        Enquanto a fonte de interações não fornecer gravidade (caso do
        Detecta Interações), as linhas ficam com gravidade NULL e
        aparecem agrupadas sob a chave None.

        Retorna: {"grave": 12, "moderada": 30, "leve": 8, None: 5, ...}
        """
        gravidade_normalizada = func.lower(func.trim(InteracoesMedicamentos.gravidade))

        linhas = (
            db.session.query(
                gravidade_normalizada.label("gravidade"),
                func.count(InteracoesMedicamentos.id).label("total"),
            )
            .group_by(gravidade_normalizada)
            .all()
        )
        return {linha.gravidade: linha.total for linha in linhas}
    
    def find_por_medicamento(self, id_catalogo: int) -> List[InteracoesMedicamentos]:
        return (
            InteracoesMedicamentos.query
            .options(selectinload(InteracoesMedicamentos.medicamento_a),
                    selectinload(InteracoesMedicamentos.medicamento_b))
            .filter(or_(
                InteracoesMedicamentos.id_medicamento_a == id_catalogo,
                InteracoesMedicamentos.id_medicamento_b == id_catalogo,
            ))
            .all()
        )

    def find_entre_medicamentos(self, ids) -> List[InteracoesMedicamentos]:
        """Interações em que os DOIS lados estão na lista de ids."""
        return (
            InteracoesMedicamentos.query
            .options(selectinload(InteracoesMedicamentos.medicamento_a),
                    selectinload(InteracoesMedicamentos.medicamento_b))
            .filter(InteracoesMedicamentos.id_medicamento_a.in_(ids),
                    InteracoesMedicamentos.id_medicamento_b.in_(ids))
            .all()
        )

    def find_cruzadas(self, ids_prescritos, ids_em_uso) -> List[InteracoesMedicamentos]:
        """Interações em que pelo menos um lado é item prescrito e o outro é
        prescrito ou já em uso pelo paciente. Não inclui em_uso x em_uso:
        isso não é efeito da prescrição atual."""
        prescritos = set(ids_prescritos or ())
        if not prescritos:
            return []
        em_uso = set(ids_em_uso or ())
        A, B = InteracoesMedicamentos.id_medicamento_a, InteracoesMedicamentos.id_medicamento_b
        condicoes = [A.in_(prescritos) & B.in_(prescritos)]
        if em_uso:
            condicoes += [A.in_(prescritos) & B.in_(em_uso),
                          A.in_(em_uso) & B.in_(prescritos)]
        return (
            InteracoesMedicamentos.query
            .options(selectinload(InteracoesMedicamentos.medicamento_a),
                     selectinload(InteracoesMedicamentos.medicamento_b))
            .filter(or_(*condicoes))
            .all()
        )

    def find_por_uuids(self, uuid: str, outros_uuids) -> List[InteracoesMedicamentos]:
        """Interações entre o medicamento `uuid` e qualquer um de `outros_uuids`
        (uuids públicos de CatalogoMedicamentos). Lista vazia se não houver
        'outros' ou se o uuid base não existir no catálogo."""
        outros_uuids = set(outros_uuids or ()) - {uuid}
        if not outros_uuids:
            return []
        linhas = (db.session.query(CatalogoMedicamentos.uuid, CatalogoMedicamentos.id)
                  .filter(CatalogoMedicamentos.uuid.in_({uuid, *outros_uuids}))
                  .all())
        ids = {u: i for u, i in linhas}
        if uuid not in ids:
            return []
        id_base = ids[uuid]
        id_outros = [i for u, i in ids.items() if u != uuid]
        if not id_outros:
            return []
        A, B = InteracoesMedicamentos.id_medicamento_a, InteracoesMedicamentos.id_medicamento_b
        return (
            InteracoesMedicamentos.query
            .options(selectinload(InteracoesMedicamentos.medicamento_a),
                     selectinload(InteracoesMedicamentos.medicamento_b))
            .filter(or_((A == id_base) & B.in_(id_outros),
                        (B == id_base) & A.in_(id_outros)))
            .all()
        )