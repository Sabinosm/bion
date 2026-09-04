from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy import func, and_, or_, tuple_

from src.models import db
from src.core.interfaces import IRepository
from src.models.auditoria import LogAcesso, LogAlteracao
from src.models.usuarios import Usuario  # ajustar path conforme o projeto

# Paginacao da listagem simples (offset/limit) -- usada em /acessos,
# /alteracoes e no resumo por profissional.
PER_PAGE_PADRAO = 10
LIMIT_MAXIMO = 50  # trava contra o front pedir um limit absurdo

# Paginacao por cursor -- usada no detalhe do profissional.
CURSOR_LIMIT_PADRAO = 10


def _limit_seguro(limit: Optional[int]) -> int:
    if not limit or limit <= 0:
        return PER_PAGE_PADRAO
    return min(limit, LIMIT_MAXIMO)


# LogAlteracao.operacao no banco e estrutural (o que o SQL de fato fez:
# INSERT/UPDATE/DELETE) -- e um fato imutavel do evento, nao deve ser
# reescrito para caber num vocabulario de filtro de UI. O filtro de
# negocio (mesma categoria usada em LogAcesso.operacao) e resolvido por
# TRADUCAO aqui, na consulta, nao gravado no banco. Isso preserva a
# granularidade real do log e ainda permite trocar a taxonomia de
# filtro no futuro sem precisar migrar dado historico.
#
# Um valor de negocio pode mapear para mais de uma operacao SQL (ex:
# "escrita" cobre tanto INSERT quanto UPDATE).
MAPA_OPERACAO_NEGOCIO_PARA_SQL = {
    "escrita": ("INSERT", "UPDATE"),
    "exclusao-logica": ("DELETE",),
}


def _operacoes_sql_para_filtro(operacao_negocio: Optional[str]) -> Optional[tuple]:
    """Traduz uma operacao de negocio (ex: 'escrita') para a tupla de
    valores INSERT/UPDATE/DELETE correspondente, para uso em .in_().
    Se o valor recebido ja for um valor SQL valido (INSERT/UPDATE/
    DELETE), usa direto -- mantem compatibilidade com quem ainda filtra
    pelo valor estrutural.

    Se o valor nao for reconhecido nem como categoria de negocio nem
    como valor SQL (ex: veio um `acao` livre tipo "editar_paciente"
    reaproveitado como `operacao`), retorna None em vez de um fallback
    que filtraria por um valor que nunca vai bater -- None sinaliza
    "nao aplicar este filtro", evitando reduzir o resultado a zero
    silenciosamente por engano de quem chamou."""
    if not operacao_negocio:
        return None
    if operacao_negocio in ("INSERT", "UPDATE", "DELETE"):
        return (operacao_negocio,)
    return MAPA_OPERACAO_NEGOCIO_PARA_SQL.get(operacao_negocio)


class AuditoriaResumoRepository:
    """Repository dedicado ao resumo por profissional (tela principal).

    E uma query so, partindo de Usuario, filtrando por EXISTS de log de
    acesso OU alteracao -- diferente de paginar LogAcesso e LogAlteracao
    separadamente e juntar depois (o que quebraria a ordenacao alfabetica
    global e o "exatamente N por pagina"). EXISTS em vez de JOIN/UNION
    porque um profissional com os dois tipos de log nao deve aparecer
    duplicado.
    """

    def find_profissionais(self, id_empresa: int, *, nome_usuario: str = None,
                            tipo_usuario: str = None, acao: str = None,
                            page: int = 1, per_page: int = PER_PAGE_PADRAO) -> Tuple[List[Usuario], int]:
        """`acao` filtra por LogAlteracao.acao (texto livre) OU
        LogAcesso.operacao (categoria fechada) -- um profissional
        aparece se bate com qualquer um dos dois lados, ja que 'acao' na
        UI e um conceito unico que cobre os dois logs."""
        existe_acesso = LogAcesso.query.filter(
            LogAcesso.id_usuario == Usuario.id_usuario,
            LogAcesso.id_empresa == id_empresa,
        )
        existe_alteracao = LogAlteracao.query.filter(
            LogAlteracao.alterado_por == Usuario.id_usuario,
            LogAlteracao.id_empresa == id_empresa,
        )

        if acao:
            existe_acesso = existe_acesso.filter(LogAcesso.operacao == acao)
            operacoes_sql = _operacoes_sql_para_filtro(acao)
            condicao_alteracao = LogAlteracao.acao == acao
            if operacoes_sql:
                condicao_alteracao = or_(condicao_alteracao, LogAlteracao.operacao.in_(operacoes_sql))
            existe_alteracao = existe_alteracao.filter(condicao_alteracao)

        query = db.session.query(Usuario).filter(
            or_(existe_acesso.exists(), existe_alteracao.exists())
        )

        if nome_usuario:
            query = query.filter(Usuario.nome.ilike(f"%{nome_usuario}%"))
        if tipo_usuario:
            query = query.filter(Usuario.tipo_usuario == tipo_usuario)  # ajustar valor conforme o model real

        per_page = _limit_seguro(per_page)
        total = query.order_by(None).count()
        itens = (query.order_by(Usuario.nome.asc())
                 .offset((page - 1) * per_page)
                 .limit(per_page)
                 .all())
        return itens, total


class LogAcessoRepository(IRepository[LogAcesso]):

    def find_by_id(self, id: int) -> Optional[LogAcesso]:
        return db.session.get(LogAcesso, id)

    def find_by_uuid(self, uuid: str) -> Optional[LogAcesso]:
        return LogAcesso.query.filter_by(uuid=uuid).first()

    def save(self, entity: LogAcesso) -> LogAcesso:
        # SEM commit() aqui de proposito. Quem chama (service/decorator)
        # decide quando commitar -- isso permite que o log entre na MESMA
        # transacao da acao que ele esta registrando, e um commit() so no
        # final.
        db.session.add(entity)
        return entity

    def delete(self, id: int) -> bool:
        # Logs de acesso são imutáveis por design (auditoria/LGPD) — exclusão não é permitida.
        return False

    def find_all(self, id_empresa: int, *, uuid_usuario: str = None,
                 nome_usuario: str = None, operacao: str = None,
                 data_inicio: datetime = None, data_fim: datetime = None,
                 page: int = 1, per_page: int = PER_PAGE_PADRAO) -> Tuple[List[LogAcesso], int]:
        """Listagem paginada e filtrada (offset/limit). Sempre escopada
        por empresa. Filtra por uuid_usuario (nunca id interno) via join
        com Usuario -- id_usuario nunca e aceito vindo de fora."""
        query = LogAcesso.query.filter(LogAcesso.id_empresa == id_empresa)

        precisa_join_usuario = uuid_usuario or nome_usuario
        if precisa_join_usuario:
            query = query.join(Usuario, Usuario.id_usuario == LogAcesso.id_usuario)
        if uuid_usuario:
            query = query.filter(Usuario.uuid == uuid_usuario)
        if nome_usuario:
            query = query.filter(Usuario.nome.ilike(f"%{nome_usuario}%"))
        if operacao:
            query = query.filter(LogAcesso.operacao == operacao)
        if data_inicio:
            query = query.filter(LogAcesso.data_hora >= data_inicio)
        if data_fim:
            query = query.filter(LogAcesso.data_hora <= data_fim)

        per_page = _limit_seguro(per_page)
        total = query.order_by(None).count()
        itens = (query.order_by(LogAcesso.data_hora.desc())
                 .offset((page - 1) * per_page)
                 .limit(per_page)
                 .all())
        return itens, total

    def find_por_usuario_cursor(self, uuid_usuario: str, id_empresa: int, *,
                                 operacao: str = None, data_inicio: datetime = None,
                                 data_fim: datetime = None, cursor_data: datetime = None,
                                 cursor_uuid: str = None,
                                 limit: int = CURSOR_LIMIT_PADRAO) -> Tuple[List[LogAcesso], bool]:
        """Historico de acesso de UM profissional, paginado por cursor de
        data (keyset pagination) em vez de offset -- estavel mesmo com
        logs novos chegando entre uma pagina e outra, o que offset nao
        garante.

        cursor_data/cursor_uuid: vem da ULTIMA linha da pagina anterior
        (o client devolve o que recebeu). Sem cursor, comeca do mais
        recente. O par (data, uuid) desempata quando dois logs tem o
        mesmo timestamp -- sem isso, dois registros no mesmo instante
        poderiam ser pulados ou repetidos entre paginas.

        Retorna (itens, tem_mais) -- `tem_mais` indica se ha proxima
        pagina, para o front decidir se mostra "carregar mais".
        """
        query = (
            LogAcesso.query
            .join(Usuario, Usuario.id_usuario == LogAcesso.id_usuario)
            .filter(LogAcesso.id_empresa == id_empresa, Usuario.uuid == uuid_usuario)
        )

        if operacao:
            query = query.filter(LogAcesso.operacao == operacao)
        if data_inicio:
            query = query.filter(LogAcesso.data_hora >= data_inicio)
        if data_fim:
            query = query.filter(LogAcesso.data_hora <= data_fim)

        if cursor_data and cursor_uuid:
            # (data_hora, uuid) < (cursor_data, cursor_uuid), comparacao
            # lexicografica de tupla -- pega tudo estritamente "antes" do
            # ultimo item ja visto, sem depender de posicao/offset.
            query = query.filter(
                tuple_(LogAcesso.data_hora, LogAcesso.uuid) < (cursor_data, cursor_uuid)
            )
        elif cursor_data:
            query = query.filter(LogAcesso.data_hora < cursor_data)

        limit = _limit_seguro(limit)
        # pede um a mais so para saber se ha proxima pagina, sem contar tudo
        itens = (query.order_by(LogAcesso.data_hora.desc(), LogAcesso.uuid.desc())
                 .limit(limit + 1)
                 .all())

        tem_mais = len(itens) > limit
        return itens[:limit], tem_mais

    def find_ultimo_por_usuarios(self, id_empresa: int, ids_usuario: List[int]) -> List[LogAcesso]:
        """Ultimo LogAcesso de cada usuario em `ids_usuario` -- usado
        para preencher 'ultimo_acesso' apenas dos profissionais que ja
        estao na pagina atual do resumo (nao mais de todo mundo de uma
        vez, ja que o resumo agora e paginado por profissional)."""
        if not ids_usuario:
            return []

        sub = (
            db.session.query(
                LogAcesso.id_usuario.label("id_usuario"),
                func.max(LogAcesso.data_hora).label("max_data")
            )
            .filter(LogAcesso.id_empresa == id_empresa, LogAcesso.id_usuario.in_(ids_usuario))
            .group_by(LogAcesso.id_usuario)
            .subquery()
        )

        return (
            db.session.query(LogAcesso)
            .join(sub, and_(
                LogAcesso.id_usuario == sub.c.id_usuario,
                LogAcesso.data_hora == sub.c.max_data,
            ))
            .filter(LogAcesso.id_empresa == id_empresa)
            .all()
        )


class LogAlteracaoRepository(IRepository[LogAlteracao]):

    def find_by_id(self, id: int) -> Optional[LogAlteracao]:
        return db.session.get(LogAlteracao, id)

    def find_by_uuid(self, uuid: str) -> Optional[LogAlteracao]:
        return LogAlteracao.query.filter_by(uuid=uuid).first()

    def find_por_registro(self, tabela_origem: str, uuid_registro: str,
                           id_empresa: int) -> List[LogAlteracao]:
        return LogAlteracao.query.filter_by(
            tabela_origem=tabela_origem, uuid_registro=uuid_registro,
            id_empresa=id_empresa,
        ).order_by(LogAlteracao.alterado_em.desc()).all()

    def save(self, entity: LogAlteracao) -> LogAlteracao:
        db.session.add(entity)
        return entity

    def delete(self, id: int) -> bool:
        # Trilha de auditoria é imutável por design — exclusão não é permitida.
        return False

    def find_all(self, id_empresa: int, *, uuid_usuario: str = None,
                 nome_usuario: str = None, acao: str = None, operacao: str = None,
                 data_inicio: datetime = None, data_fim: datetime = None,
                 page: int = 1, per_page: int = PER_PAGE_PADRAO) -> Tuple[List[LogAlteracao], int]:
        """Listagem paginada e filtrada (offset/limit). Sempre escopada
        por empresa. Filtra por uuid_usuario (nunca id interno)."""
        query = LogAlteracao.query.filter(LogAlteracao.id_empresa == id_empresa)

        precisa_join_usuario = uuid_usuario or nome_usuario
        if precisa_join_usuario:
            query = query.join(Usuario, Usuario.id_usuario == LogAlteracao.alterado_por)
        if uuid_usuario:
            query = query.filter(Usuario.uuid == uuid_usuario)
        if nome_usuario:
            query = query.filter(Usuario.nome.ilike(f"%{nome_usuario}%"))
        if acao:
            query = query.filter(LogAlteracao.acao == acao)
        if operacao:
            # operacao aqui e a categoria de negocio (leitura/escrita/
            # exclusao-logica/exportacao, mesmo vocabulario do filtro de
            # LogAcesso) -- traduzida para INSERT/UPDATE/DELETE, que e o
            # que de fato esta gravado na coluna. Se nao reconhecido
            # (None), nao aplica o filtro -- ver _operacoes_sql_para_filtro.
            operacoes_sql = _operacoes_sql_para_filtro(operacao)
            if operacoes_sql:
                query = query.filter(LogAlteracao.operacao.in_(operacoes_sql))
        if data_inicio:
            query = query.filter(LogAlteracao.alterado_em >= data_inicio)
        if data_fim:
            query = query.filter(LogAlteracao.alterado_em <= data_fim)

        per_page = _limit_seguro(per_page)
        total = query.order_by(None).count()
        itens = (query.order_by(LogAlteracao.alterado_em.desc())
                  .offset((page - 1) * per_page)
                  .limit(per_page)
                  .all())
        return itens, total

    def find_por_usuario_cursor(self, uuid_usuario: str, id_empresa: int, *,
                                 acao: str = None, operacao: str = None,
                                 data_inicio: datetime = None, data_fim: datetime = None,
                                 cursor_data: datetime = None, cursor_uuid: str = None,
                                 limit: int = CURSOR_LIMIT_PADRAO) -> Tuple[List[LogAlteracao], bool]:
        """Historico de alteracao de UM profissional, paginado por cursor
        de data. Mesma logica de find_por_usuario_cursor de LogAcesso."""
        query = (
            LogAlteracao.query
            .join(Usuario, Usuario.id_usuario == LogAlteracao.alterado_por)
            .filter(LogAlteracao.id_empresa == id_empresa, Usuario.uuid == uuid_usuario)
        )

        if acao:
            query = query.filter(LogAlteracao.acao == acao)
        if operacao:
            operacoes_sql = _operacoes_sql_para_filtro(operacao)
            if operacoes_sql:
                query = query.filter(LogAlteracao.operacao.in_(operacoes_sql))
        if data_inicio:
            query = query.filter(LogAlteracao.alterado_em >= data_inicio)
        if data_fim:
            query = query.filter(LogAlteracao.alterado_em <= data_fim)

        if cursor_data and cursor_uuid:
            query = query.filter(
                tuple_(LogAlteracao.alterado_em, LogAlteracao.uuid) < (cursor_data, cursor_uuid)
            )
        elif cursor_data:
            query = query.filter(LogAlteracao.alterado_em < cursor_data)

        limit = _limit_seguro(limit)
        itens = (query.order_by(LogAlteracao.alterado_em.desc(), LogAlteracao.uuid.desc())
                 .limit(limit + 1)
                 .all())

        tem_mais = len(itens) > limit
        return itens[:limit], tem_mais

    def find_ultimo_por_usuarios(self, id_empresa: int, ids_usuario: List[int]) -> List[LogAlteracao]:
        """Ultima LogAlteracao de cada usuario em `ids_usuario`."""
        if not ids_usuario:
            return []

        sub = (
            db.session.query(
                LogAlteracao.alterado_por.label("alterado_por"),
                func.max(LogAlteracao.alterado_em).label("max_data")
            )
            .filter(LogAlteracao.id_empresa == id_empresa,
                    LogAlteracao.alterado_por.in_(ids_usuario))
            .group_by(LogAlteracao.alterado_por)
            .subquery()
        )

        return (
            db.session.query(LogAlteracao)
            .join(sub, and_(
                LogAlteracao.alterado_por == sub.c.alterado_por,
                LogAlteracao.alterado_em == sub.c.max_data,
            ))
            .filter(LogAlteracao.id_empresa == id_empresa)
            .all()
        )