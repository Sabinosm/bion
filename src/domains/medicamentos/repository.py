from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.catalogos.catalogo_exames import CatalogoExames
from src.models.catalogos.catalogo_medicamentos import CatalogoMedicamentos
from src.models.catalogos.interacoes_medicamentos import InteracoesMedicamentos


class CatalogoMedicamentosRepository(IRepository[CatalogoMedicamentos]):

    def find_by_id(self, id: int) -> Optional[CatalogoMedicamentos]:
        return db.session.get(CatalogoMedicamentos, id)

    def find_by_uuid(self, uuid: str) -> Optional[CatalogoMedicamentos]:
        return CatalogoMedicamentos.query.filter_by(uuid=uuid).first()

    def buscar_por_principio_ativo(self, termo: str) -> List[CatalogoMedicamentos]:
        return CatalogoMedicamentos.query.filter(
            CatalogoMedicamentos.principio_ativo.ilike(f"%{termo}%")
        ).limit(20).all()

    def interacoes_de(self, id_medicamento: int) -> List[InteracoesMedicamentos]:
        return InteracoesMedicamentos.query.filter(
            (InteracoesMedicamentos.id_medicamento_a == id_medicamento) |
            (InteracoesMedicamentos.id_medicamento_b == id_medicamento)
        ).all()

    def save(self, entity: CatalogoMedicamentos) -> CatalogoMedicamentos:
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

    def find_all(self) -> List[CatalogoMedicamentos]:
        return CatalogoMedicamentos.query.all()

class InteracoesMedicamentosRepository(IRepository[InteracoesMedicamentos]):

    def find_by_id(self, id: int) -> Optional[InteracoesMedicamentos]:
        return db.session.get(InteracoesMedicamentos, id)

    def find_by_uuid(self, uuid: str) -> Optional[InteracoesMedicamentos]:
        return InteracoesMedicamentos.query.filter_by(uuid=uuid).first()

    def find_por_medicamento(self, id_catalogo: int) -> List[InteracoesMedicamentos]:
        """Todas as interações que envolvem um medicamento, seja como A ou B."""
        from sqlalchemy import or_
        return (
            InteracoesMedicamentos.query
            .filter(or_(
                InteracoesMedicamentos.id_medicamento_a == id_catalogo,
                InteracoesMedicamentos.id_medicamento_b == id_catalogo,
            ))
            .all()
        )

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
 
        Retorna: {"grave": 12, "moderada": 30, "leve": 8, ...}
        """
        from sqlalchemy import func
 
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