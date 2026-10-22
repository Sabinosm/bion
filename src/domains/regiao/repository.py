"""
repository.py

Acesso a dados do domínio Região Geográfica (municípios, estados e demais
unidades territoriais). O tipo de uma região não é uma coluna de texto: vive na
tabela de tipos de jurisdição, ligada por chave estrangeira, e o campo `codigo`
dessa tabela guarda a mesma string que o enum antigo usava ("municipio",
"estado" etc.). Por isso a busca por tipo faz um JOIN explícito com a tabela de
tipos, em vez de filtrar a região diretamente.

Cada gravação confirma a transação. Como o service tolera falhas de gravação
(devolve None em vez de propagar), o repository também expõe o rollback, para a
sessão do banco não ficar inutilizável depois de uma falha.
"""

from typing import Optional, List, Tuple

from src.models import db
from src.core.interfaces import IRepository
from src.models.corp import RegiaoGeografica
from src.models.corp.tipo_jurisdicao import TipoJurisdicao


# Paginação da listagem: tamanho padrão da página e teto, para o front não
# pedir uma página gigante.
PER_PAGE_PADRAO = 15
LIMIT_MAXIMO = 50


def limit_seguro(limit: Optional[int]) -> int:
    """Normaliza o tamanho da página: vazio ou não positivo vira o padrão; acima do máximo é cortado."""
    if not limit or limit <= 0:
        return PER_PAGE_PADRAO
    return min(limit, LIMIT_MAXIMO)


class RegiaoRepository(IRepository[RegiaoGeografica]):

    def find_by_id(self, id: int) -> Optional[RegiaoGeografica]:
        return db.session.get(RegiaoGeografica, id)

    def find_by_uuid(self, uuid: str) -> Optional[RegiaoGeografica]:
        return RegiaoGeografica.query.filter_by(uuid=uuid).first()

    def find_by_codigo_ibge(self, codigo: str) -> Optional[RegiaoGeografica]:
        return RegiaoGeografica.query.filter_by(codigo_ibge=codigo).first()

    def find_por_tipo(self, tipo: str) -> List[RegiaoGeografica]:
        """Regiões de um tipo, identificado pela string de sempre (ex.: "municipio")."""
        return (
            RegiaoGeografica.query
            .join(TipoJurisdicao, TipoJurisdicao.id == RegiaoGeografica.id_tipo_jurisdicao)
            .filter(TipoJurisdicao.codigo == tipo)
            .all()
        )

    def find_all(self) -> List[RegiaoGeografica]:
        return RegiaoGeografica.query.all()

    def find_paginado(
        self, tipo: Optional[str] = None, page: int = 1, per_page: int = PER_PAGE_PADRAO
    ) -> Tuple[List[RegiaoGeografica], int]:
        """Uma página de regiões em ordem alfabética, todas ou só de um tipo.

        A ordenação por nome, com o id como desempate, mantém a paginação
        estável entre uma chamada e outra.

        Returns:
            (itens, total), onde `total` é a contagem de todas as regiões do
            filtro, e não só as da página.
        """
        per_page = limit_seguro(per_page)
        query = RegiaoGeografica.query
        if tipo:
            query = (
                query
                .join(TipoJurisdicao, TipoJurisdicao.id == RegiaoGeografica.id_tipo_jurisdicao)
                .filter(TipoJurisdicao.codigo == tipo)
            )

        total = query.order_by(None).count()
        itens = (
            query
            .order_by(RegiaoGeografica.nome_regiao.asc(), RegiaoGeografica.id.asc())
            .offset((max(page, 1) - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return itens, total

    def find_tipo_jurisdicao_por_codigo(self, codigo: str) -> Optional[TipoJurisdicao]:
        """Tipo de jurisdição pelo código (ex.: "municipio"), ou None se não estiver cadastrado."""
        return TipoJurisdicao.query.filter_by(codigo=codigo).first()

    def save(self, entity: RegiaoGeografica) -> RegiaoGeografica:
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

    def rollback(self):
        """Desfaz a transação em andamento, para a sessão voltar a ser utilizável depois de uma falha."""
        db.session.rollback()