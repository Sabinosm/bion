from typing import Optional, List
from src.domains.medicamentos.normalizacao import normalizar_nome
from src.models import db
from src.core.interfaces import IRepository
from src.models.catalogos.catalogo_medicamentos import CatalogoMedicamentos
from src.models.catalogos.interacoes_medicamentos import InteracoesMedicamentos


class CatalogoMedicamentosRepository(IRepository[CatalogoMedicamentos]):

    def find_by_id(self, id: int) -> Optional[CatalogoMedicamentos]:
        return db.session.get(CatalogoMedicamentos, id)

    def existe_por_id(self, id: int) -> bool:
        """Checagem de existência para validação de FK (ex:
        MedicamentoEmUsoService ao registrar um medicamento em uso).
        Usa a mesma query de find_by_id -- método próprio só para
        deixar a intenção clara no ponto de chamada (checar existência,
        não usar a entidade)."""
        return self.find_by_id(id) is not None

    def find_by_uuid(self, uuid: str) -> Optional[CatalogoMedicamentos]:
        return CatalogoMedicamentos.query.filter_by(uuid=uuid).first()

    def buscar_por_principio_ativo(self, termo: str) -> List[CatalogoMedicamentos]:
        return CatalogoMedicamentos.query.filter(
            CatalogoMedicamentos.principio_ativo.ilike(f"%{termo}%")
        ).limit(20).all()

    def find_por_principio_ativo_exato(self, principio_ativo: str) -> Optional[CatalogoMedicamentos]:
        """Busca exata (case-insensitive), usada pelo processo de
        sincronização para decidir se um item da fonte externa já
        existe no catálogo (update) ou é novo (insert). Não confundir
        com buscar_por_principio_ativo, que é fuzzy e para uso do
        médico/IA."""
        return CatalogoMedicamentos.query.filter(
            db.func.lower(CatalogoMedicamentos.principio_ativo) == principio_ativo.lower()
        ).first()

    def interacoes_de(self, id_medicamento: int) -> List[InteracoesMedicamentos]:
        return InteracoesMedicamentos.query.filter(
            (InteracoesMedicamentos.id_medicamento_a == id_medicamento) |
            (InteracoesMedicamentos.id_medicamento_b == id_medicamento)
        ).all()

    def save(self, entity: CatalogoMedicamentos) -> CatalogoMedicamentos:
        # Catálogo é somente-leitura para o fluxo normal da aplicação
        # (médico, IA, etc). Este método existe para cumprir o
        # contrato IRepository e é usado exclusivamente pelo
        # AtualizacaoMedicamentosService (ver
        # atualizacao_medicamentos_service.py) -- o único ponto
        # autorizado a criar/editar linhas do catálogo, sincronizando
        # com a fonte externa. CatalogoMedicamentosService (uso comum)
        # não deve chamar save/delete.
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
    
    from src.domains.medicamentos.normalizacao import normalizar_nome  # no topo do arquivo

    def find_por_nome_normalizado(self, principio_ativo: str) -> Optional[CatalogoMedicamentos]:
        """Busca pelo nome normalizado (sem acento, minúsculo, sem
        prefixo de sal), usando a coluna indexada
        principio_ativo_normalizado. Usada pela sincronização para
        decidir entre criar e atualizar."""
        return CatalogoMedicamentos.query.filter_by(
            principio_ativo_normalizado=normalizar_nome(principio_ativo)
        ).first()

    def add(self, entity: CatalogoMedicamentos) -> CatalogoMedicamentos:
        """Adiciona à sessão e faz flush (gera o id para o log), SEM
        commit. O commit em lotes fica por conta do
        AtualizacaoMedicamentosService. Diferente de save(), que
        commita a cada chamada."""
        db.session.add(entity)
        db.session.flush()
        return entity
