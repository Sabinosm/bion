from typing import Optional, List
from src.domains.medicamentos.normalizacao import normalizar_nome
from src.models import db
from src.core.interfaces import IRepository
from src.models.catalogos.catalogo_medicamentos import CatalogoMedicamentos, CatalogoMedicamentosSinonimo
from src.models.catalogos.interacoes_medicamentos import InteracoesMedicamentos
from src.models.catalogos.indicacao_terapeutica import IndicacaoTerapeutica
from sqlalchemy import cast
from src.core.consultas import escapar_like
from src.models.catalogos.contraindicacao import Contraindicacao



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

    @staticmethod
    def _filtro_busca(termo: str):
        t = termo.strip()
        p_norm = f"%{escapar_like(normalizar_nome(t))}%"
        p_raw = f"%{escapar_like(t.lower())}%"
        return db.or_(
            CatalogoMedicamentos.principio_ativo_normalizado.like(p_norm, escape="\\"),
            CatalogoMedicamentos.principio_ativo.ilike(p_raw, escape="\\"),
            CatalogoMedicamentos.sinonimos.any(
                CatalogoMedicamentosSinonimo.nome_normalizado.like(p_norm, escape="\\")),
            db.func.lower(cast(CatalogoMedicamentos.nomes_comerciais_json, db.Text)).like(p_raw, escape="\\"),
        )

    def listar_paginado(self, termo, pagina: int, por_pagina: int,
                        uuid_indicacao=None, uuids_sem_contraindicacao=None, classe=None):
        q = CatalogoMedicamentos.query
        if classe:
            q = q.filter(db.func.lower(CatalogoMedicamentos.classe_farmaceutica) == classe.lower())
        if uuid_indicacao:
            q = q.filter(CatalogoMedicamentos.indicacoes_terapeuticas.any(
                IndicacaoTerapeutica.uuid == uuid_indicacao))
        if uuids_sem_contraindicacao:
            q = q.filter(~CatalogoMedicamentos.contraindicacoes.any(
                Contraindicacao.uuid.in_(uuids_sem_contraindicacao)))
        ordem = [CatalogoMedicamentos.principio_ativo]
        if termo and termo.strip():
            q = q.filter(self._filtro_busca(termo))
            t = normalizar_nome(termo)
            prioridade = db.case(
                (CatalogoMedicamentos.principio_ativo_normalizado == t, 0),
                (CatalogoMedicamentos.principio_ativo_normalizado.like(f"{escapar_like(t)}%", escape="\\"), 1),
                else_=2,
            )
            ordem.insert(0, prioridade)
        return q.order_by(*ordem).paginate(page=pagina, per_page=por_pagina, error_out=False)

    def listar_classes(self):
        linhas = (db.session.query(CatalogoMedicamentos.classe_farmaceutica)
                .filter(CatalogoMedicamentos.classe_farmaceutica.isnot(None),
                        CatalogoMedicamentos.classe_farmaceutica != "")
                .distinct().order_by(CatalogoMedicamentos.classe_farmaceutica).all())
        return [l[0] for l in linhas]

    def existe_indicacao(self, uuid: str) -> bool:
        return db.session.query(IndicacaoTerapeutica.id).filter(
            IndicacaoTerapeutica.uuid == uuid).first() is not None

    def uuids_contraindicacao_existentes(self, uuids) -> set:
        linhas = db.session.query(Contraindicacao.uuid).filter(Contraindicacao.uuid.in_(uuids)).all()
        return {l[0] for l in linhas}

    def find_by_uuids(self, uuids):
        return CatalogoMedicamentos.query.filter(CatalogoMedicamentos.uuid.in_(uuids)).all()