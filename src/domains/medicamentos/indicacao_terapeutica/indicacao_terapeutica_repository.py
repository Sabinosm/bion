from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.catalogos.indicacao_terapeutica import IndicacaoTerapeutica
from src.models.catalogos.catalogo_medicamentos import CatalogoMedicamentos


class IndicacaoTerapeuticaRepository(IRepository[IndicacaoTerapeutica]):

    def find_by_id(self, id: int) -> Optional[IndicacaoTerapeutica]:
        return db.session.get(IndicacaoTerapeutica, id)

    def find_by_uuid(self, uuid: str) -> Optional[IndicacaoTerapeutica]:
        return IndicacaoTerapeutica.query.filter_by(uuid=uuid).first()

    def find_all(self) -> List[IndicacaoTerapeutica]:
        return IndicacaoTerapeutica.query.all()

    def buscar_por_nome(self, termo: str) -> List[IndicacaoTerapeutica]:
        """Busca por nome ou sinônimo. Lista é pequena e curada (ver
        decisão original), então ilike simples é suficiente -- não há
        necessidade de full-text search aqui."""
        termo_like = f"%{termo}%"
        return IndicacaoTerapeutica.query.filter(
            db.or_(
                IndicacaoTerapeutica.nome.ilike(termo_like),
                db.func.json_search(
                    IndicacaoTerapeutica.sinonimos_busca_json, "one", termo_like
                ).isnot(None),
            )
        ).all()

    def medicamentos_da_indicacao(self, id_indicacao: int) -> List[CatalogoMedicamentos]:
        """Sentido sintoma -> medicamentos: dado um id de indicação,
        retorna todo o catálogo ligado a ela."""
        indicacao = self.find_by_id(id_indicacao)
        return indicacao.medicamentos if indicacao else []

    def save(self, entity: IndicacaoTerapeutica) -> IndicacaoTerapeutica:
        # Lista curada e fechada, mesmo padrão de CatalogoMedicamentos:
        # sem caminho de criação livre por usuário comum. Método
        # mantido para cumprir o contrato IRepository e para uso
        # interno de curadoria/seed, não exposto por controller.
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