from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.catalogos.contraindicacao import Contraindicacao
from src.models.catalogos.catalogo_medicamentos import CatalogoMedicamentos


class ContraindicacaoRepository(IRepository[Contraindicacao]):

    def find_by_id(self, id: int) -> Optional[Contraindicacao]:
        return db.session.get(Contraindicacao, id)

    def find_by_uuid(self, uuid: str) -> Optional[Contraindicacao]:
        return Contraindicacao.query.filter_by(uuid=uuid).first()

    def find_all(self) -> List[Contraindicacao]:
        return Contraindicacao.query.all()

    def buscar_por_nome(self, termo: str) -> List[Contraindicacao]:
        """Lista curada e pequena (ver decisão original) -- ilike
        simples é suficiente, sem sinônimo/JSON como em
        IndicacaoTerapeutica."""
        return Contraindicacao.query.filter(
            Contraindicacao.nome.ilike(f"%{termo}%")
        ).all()

    def medicamentos_da_contraindicacao(self, id_contraindicacao: int) -> List[CatalogoMedicamentos]:
        """Sentido condição -> medicamentos contraindicados: dado um
        id de contraindicação, retorna todo o catálogo ligado a ela."""
        contraindicacao = self.find_by_id(id_contraindicacao)
        return contraindicacao.medicamentos if contraindicacao else []

    def save(self, entity: Contraindicacao) -> Contraindicacao:
        # Lista curada e fechada, mesmo padrão de CatalogoMedicamentos
        # e IndicacaoTerapeutica: sem caminho de criação livre por
        # usuário comum. Método mantido para cumprir o contrato
        # IRepository e uso interno de curadoria/seed.
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