from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.core.consultas import escapar_like
from src.models.catalogos.catalogo_exames import CatalogoExames
from .normalizacao import normalizar_texto

class CatalogoExamesRepository(IRepository[CatalogoExames]):

    def find_by_id(self, id: int) -> Optional[CatalogoExames]:
        return db.session.get(CatalogoExames, id)

    def find_by_uuid(self, uuid: str) -> Optional[CatalogoExames]:
        return CatalogoExames.query.filter_by(uuid=uuid).first()

    @staticmethod
    def _filtro_busca(termo: str):
        """Casa nome (pt), nome em inglês e sinônimos, sem diferenciar acento nem maiúscula
        (busca_normalizada). Linhas ainda sem busca_normalizada (criadas fora da importação)
        continuam acháveis pelo nome_exame."""
        padrao = f"%{escapar_like(normalizar_texto(termo))}%"
        return db.or_(
            CatalogoExames.busca_normalizada.like(padrao, escape="\\"),
            CatalogoExames.nome_exame.ilike(f"%{escapar_like(termo.strip())}%", escape="\\"),
        )

    def buscar_por_nome(self, termo: str) -> List[CatalogoExames]:
        return (
            CatalogoExames.query
            .filter(self._filtro_busca(termo), CatalogoExames.ativo.is_(True))
            .order_by(CatalogoExames.nome_exame)
            .limit(20).all()
        )

    def listar_paginado(self, termo: Optional[str], tipo: Optional[str], pagina: int, por_pagina: int,
                    material: Optional[str] = None, exige_jejum: Optional[bool] = None):
        """Só exames ativos. Com termo: nome exato primeiro, depois nome que começa com o termo,
        depois o restante (por nome)."""
        q = CatalogoExames.query.filter(CatalogoExames.ativo.is_(True))
        if tipo:
            q = q.filter(CatalogoExames.tipo == tipo)
        if material:
            q = q.filter(db.func.lower(CatalogoExames.material) == material.lower())
        if exige_jejum is True:
            q = q.filter(CatalogoExames.jejum_horas > 0)
        elif exige_jejum is False:
            q = q.filter(db.or_(CatalogoExames.jejum_horas.is_(None), CatalogoExames.jejum_horas == 0))
        ordem = [CatalogoExames.nome_exame]
        if termo and termo.strip():
            q = q.filter(self._filtro_busca(termo))
            t = normalizar_texto(termo)
            prioridade = db.case(
                (CatalogoExames.nome_normalizado == t, 0),
                (CatalogoExames.nome_normalizado.like(f"{escapar_like(t)}%", escape="\\"), 1),
                else_=2,
            )
            ordem.insert(0, prioridade)
        return q.order_by(*ordem).paginate(page=pagina, per_page=por_pagina, error_out=False)

    def listar_materiais(self) -> List[str]:
        linhas = (db.session.query(CatalogoExames.material)
                .filter(CatalogoExames.ativo.is_(True),
                        CatalogoExames.material.isnot(None), CatalogoExames.material != "")
                .distinct().order_by(CatalogoExames.material).all())
        return [l[0] for l in linhas]

    def find_por_nome_normalizado(self, nome_normalizado: str) -> Optional[CatalogoExames]:
        return CatalogoExames.query.filter_by(nome_normalizado=nome_normalizado).first()

    def save(self, entity: CatalogoExames) -> CatalogoExames:
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

    def find_all(self) -> List[CatalogoExames]:
        return CatalogoExames.query.all()



