from typing import Optional, List

from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from src.models import db
from src.core.interfaces import IRepository
from src.models.catalogos.interacoes_medicamentos import InteracoesMedicamentos

class InteracoesMedicamentosRepository(IRepository[InteracoesMedicamentos]):

    def find_by_id(self, id: int) -> Optional[InteracoesMedicamentos]:
        return db.session.get(InteracoesMedicamentos, id)

    def find_by_uuid(self, uuid: str) -> Optional[InteracoesMedicamentos]:
        return InteracoesMedicamentos.query.filter_by(uuid=uuid).first()

    def find_por_medicamento(self, id_catalogo: int) -> List[InteracoesMedicamentos]:
        """Todas as interações que envolvem um medicamento, seja como A ou B."""
        return (
            InteracoesMedicamentos.query
            .filter(or_(
                InteracoesMedicamentos.id_medicamento_a == id_catalogo,
                InteracoesMedicamentos.id_medicamento_b == id_catalogo,
            ))
            .all()
        )

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