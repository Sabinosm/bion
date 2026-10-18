"""
repository.py

Acesso a dados do domínio de Auditoria: consultas aos logs de acesso e de
alteração e ao resumo de atividade por profissional.

Os logs são append-only: a gravação apenas adiciona a entidade à sessão, sem
commit (quem orquestra decide quando commitar, para o log entrar na mesma
transação da ação auditada), e a exclusão é sempre recusada. Toda consulta é
escopada pela empresa e filtra usuários pelo uuid, nunca pelo id interno
recebido de fora.

Há dois estilos de paginação: offset/limit nas listagens simples, com limite
máximo travado, e cursor por data com desempate por uuid (keyset) no histórico
de um profissional, que não pula nem repete itens quando chegam logs novos
entre uma página e outra.
"""

from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy import func, and_, or_, tuple_

from src.models import db
from src.core.interfaces import IRepository
from src.models.auditoria import LogAcesso, LogAlteracao
from src.models.usuarios import Usuario

# Paginação offset/limit (listagens simples e resumo por profissional).
PER_PAGE_PADRAO = 10
LIMIT_MAXIMO = 50  # trava contra o front pedir um limit absurdo

# Paginação por cursor (detalhe do profissional).
CURSOR_LIMIT_PADRAO = 10

# LogAlteracao.operacao guarda o que o SQL de fato fez (INSERT/UPDATE/DELETE),
# fato imutável do evento. O vocabulário de filtro da UI (o mesmo de
# LogAcesso.operacao) é resolvido por tradução na consulta, sem ser gravado,
# o que permite mudar a taxonomia de filtro sem migrar dados históricos.
# Um valor de negócio pode mapear para mais de uma operação SQL.
MAPA_OPERACAO_NEGOCIO_PARA_SQL = {
    "escrita": ("INSERT", "UPDATE"),
    "exclusao-logica": ("DELETE",),
}


# ----------------------------------------------------------------------
# Helpers de consulta
# ----------------------------------------------------------------------

def _limit_seguro(limit: Optional[int]) -> int:
    """Normaliza o limit: vazio ou não positivo vira o padrão; acima do máximo é cortado."""
    if not limit or limit <= 0:
        return PER_PAGE_PADRAO
    return min(limit, LIMIT_MAXIMO)


def _operacoes_sql_para_filtro(operacao_negocio: Optional[str]) -> Optional[tuple]:
    """Traduz uma operação de negócio (ex.: 'escrita') nas operações SQL correspondentes, para uso em .in_().

    Um valor já estrutural (INSERT/UPDATE/DELETE) é usado direto.

    Retorno:
        None: nenhum filtro pedido; o chamador não deve filtrar.
        tupla não vazia: aplicar `.in_(tupla)`.
        tupla vazia: o valor não tem equivalente SQL (ex.: 'leitura' para
            alterações); o chamador deve aplicar `.in_(())`, que nunca bate,
            para devolver lista vazia em vez de ignorar o filtro.
    """
    if not operacao_negocio:
        return None
    if operacao_negocio in ("INSERT", "UPDATE", "DELETE"):
        return (operacao_negocio,)
    return MAPA_OPERACAO_NEGOCIO_PARA_SQL.get(operacao_negocio, ())


def _condicao_acao_alteracao(acao: str):
    """Condição de LogAlteracao para o filtro `acao` da UI: texto livre OU operação SQL traduzida da categoria."""
    condicao = LogAlteracao.acao == acao
    operacoes_sql = _operacoes_sql_para_filtro(acao)
    if operacoes_sql:
        condicao = or_(condicao, LogAlteracao.operacao.in_(operacoes_sql))
    return condicao


def _filtrar_usuario(query, coluna_usuario, uuid_usuario: Optional[str], nome_usuario: Optional[str]):
    """Filtra por uuid e/ou nome do usuário, fazendo o join com Usuario só quando necessário."""
    if uuid_usuario or nome_usuario:
        query = query.join(Usuario, Usuario.id == coluna_usuario)
    if uuid_usuario:
        query = query.filter(Usuario.uuid == uuid_usuario)
    if nome_usuario:
        query = query.filter(Usuario.nome_completo.ilike(f"%{nome_usuario}%"))
    return query


def _filtrar_periodo(query, coluna_data, data_inicio: Optional[datetime], data_fim: Optional[datetime]):
    """Restringe a coluna de data ao intervalo [data_inicio, data_fim], cada ponta opcional."""
    if data_inicio:
        query = query.filter(coluna_data >= data_inicio)
    if data_fim:
        query = query.filter(coluna_data <= data_fim)
    return query


def _filtrar_cursor(query, coluna_data, coluna_uuid, cursor_data: Optional[datetime],
                    cursor_uuid: Optional[str]):
    """Mantém só os itens estritamente anteriores ao cursor (último item já visto).

    Com data e uuid compara a tupla (data, uuid), o que desempata logs no mesmo
    instante. Só com data, compara apenas a data.
    """
    if cursor_data and cursor_uuid:
        return query.filter(tuple_(coluna_data, coluna_uuid) < (cursor_data, cursor_uuid))
    if cursor_data:
        return query.filter(coluna_data < cursor_data)
    return query


def _paginar_offset(query, ordem: tuple, page: int, per_page: int):
    """Aplica ordenação e offset/limit. Retorna (itens, total)."""
    per_page = _limit_seguro(per_page)
    total = query.order_by(None).count()
    itens = (query.order_by(*ordem)
             .offset((page - 1) * per_page)
             .limit(per_page)
             .all())
    return itens, total


def _paginar_cursor(query, coluna_data, coluna_uuid, limit: int):
    """Ordena do mais recente ao mais antigo e devolve (itens, tem_mais).

    Busca um item a mais só para saber se existe próxima página, sem contar tudo.
    """
    limit = _limit_seguro(limit)
    itens = (query.order_by(coluna_data.desc(), coluna_uuid.desc())
             .limit(limit + 1)
             .all())
    return itens[:limit], len(itens) > limit


def _ultimo_log_por_usuario(modelo, coluna_usuario, coluna_data, id_empresa: int,
                            ids_usuario: List[int]) -> list:
    """Retorna o log mais recente de cada usuário de `ids_usuario`, dentro da empresa."""
    if not ids_usuario:
        return []

    ultimos = (
        db.session.query(
            coluna_usuario.label("id_usuario"),
            func.max(coluna_data).label("max_data"),
        )
        .filter(modelo.id_empresa == id_empresa, coluna_usuario.in_(ids_usuario))
        .group_by(coluna_usuario)
        .subquery()
    )

    return (
        db.session.query(modelo)
        .join(ultimos, and_(
            coluna_usuario == ultimos.c.id_usuario,
            coluna_data == ultimos.c.max_data,
        ))
        .filter(modelo.id_empresa == id_empresa)
        .all()
    )


# ----------------------------------------------------------------------
# Repositories
# ----------------------------------------------------------------------

class AuditoriaResumoRepository:
    """Resumo por profissional (tela principal), em uma única query partindo de Usuario.

    Filtra por EXISTS de log de acesso OU de alteração. Paginar os dois logs
    separadamente e juntar depois quebraria a ordenação alfabética global e o
    "exatamente N por página"; EXISTS (em vez de JOIN/UNION) evita duplicar
    quem tem os dois tipos de log.
    """

    def find_profissionais(self, id_empresa: int, *, nome_usuario: Optional[str] = None,
                           funcao_clinica: Optional[str] = None, is_admin: Optional[bool] = None,
                           acao: Optional[str] = None, page: int = 1,
                           per_page: int = PER_PAGE_PADRAO) -> Tuple[List[Usuario], int]:
        """Página de usuários com atividade auditada, em ordem alfabética. Retorna (itens, total).

        Args:
            acao: conceito único na UI que cobre os dois logs. O profissional
                aparece se bater com LogAcesso.operacao ou com
                LogAlteracao.acao (texto livre), ou ainda com a operação SQL
                traduzida de uma categoria de negócio.
            funcao_clinica: "medico" ou "enfermeiro"; filtra por
                PapelProfissional.tipo_papel ativo, via JOIN.
            is_admin: filtra por Usuario.is_admin.

            funcao_clinica e is_admin são independentes e combináveis
            (ex.: "medico" + True = admins que também são médicos). None
            significa não filtrar naquele eixo.
        """
        existe_acesso = LogAcesso.query.filter(
            LogAcesso.id_usuario == Usuario.id,
            LogAcesso.id_empresa == id_empresa,
        )
        existe_alteracao = LogAlteracao.query.filter(
            LogAlteracao.alterado_por == Usuario.id,
            LogAlteracao.id_empresa == id_empresa,
        )

        if acao:
            existe_acesso = existe_acesso.filter(LogAcesso.operacao == acao)
            existe_alteracao = existe_alteracao.filter(_condicao_acao_alteracao(acao))

        query = db.session.query(Usuario).filter(
            or_(existe_acesso.exists(), existe_alteracao.exists())
        )

        if nome_usuario:
            query = query.filter(Usuario.nome_completo.ilike(f"%{nome_usuario}%"))

        if is_admin is not None:
            query = query.filter(Usuario.is_admin == is_admin)

        if funcao_clinica:
            from src.models.usuarios.papel_profissional import PapelProfissional
            query = query.join(
                PapelProfissional, PapelProfissional.id_usuario == Usuario.id
            ).filter(
                PapelProfissional.tipo_papel == funcao_clinica,
                PapelProfissional.ativo == True,  # noqa: E712
            )

        return _paginar_offset(query, (Usuario.nome_completo.asc(),), page, per_page)


class LogAcessoRepository(IRepository[LogAcesso]):

    def find_by_id(self, id: int) -> Optional[LogAcesso]:
        return db.session.get(LogAcesso, id)

    def find_by_uuid(self, uuid: str) -> Optional[LogAcesso]:
        return LogAcesso.query.filter_by(uuid=uuid).first()

    def save(self, entity: LogAcesso) -> LogAcesso:
        """Adiciona o log à sessão, sem commit (o commit fica com quem orquestra a transação)."""
        db.session.add(entity)
        return entity

    def delete(self, id: int) -> bool:
        """Sempre False: logs de acesso são imutáveis por design (auditoria/LGPD)."""
        return False

    def find_all(self, id_empresa: int, *, uuid_usuario: Optional[str] = None,
                 nome_usuario: Optional[str] = None, operacao: Optional[str] = None,
                 data_inicio: Optional[datetime] = None, data_fim: Optional[datetime] = None,
                 page: int = 1, per_page: int = PER_PAGE_PADRAO) -> Tuple[List[LogAcesso], int]:
        """Listagem filtrada e paginada (offset/limit), escopada por empresa. Retorna (itens, total)."""
        query = LogAcesso.query.filter(LogAcesso.id_empresa == id_empresa)
        query = _filtrar_usuario(query, LogAcesso.id_usuario, uuid_usuario, nome_usuario)
        if operacao:
            query = query.filter(LogAcesso.operacao == operacao)
        query = _filtrar_periodo(query, LogAcesso.data_hora, data_inicio, data_fim)

        return _paginar_offset(query, (LogAcesso.data_hora.desc(),), page, per_page)

    def find_por_usuario_cursor(self, uuid_usuario: str, id_empresa: int, *,
                                operacao: Optional[str] = None,
                                data_inicio: Optional[datetime] = None,
                                data_fim: Optional[datetime] = None,
                                cursor_data: Optional[datetime] = None,
                                cursor_uuid: Optional[str] = None,
                                limit: int = CURSOR_LIMIT_PADRAO) -> Tuple[List[LogAcesso], bool]:
        """Histórico de acesso de UM profissional, paginado por cursor (keyset).

        `cursor_data`/`cursor_uuid` vêm da última linha da página anterior; sem
        cursor, começa do mais recente. O uuid desempata logs no mesmo
        timestamp, evitando que sejam pulados ou repetidos entre páginas.

        Returns:
            (itens, tem_mais), onde `tem_mais` indica se há próxima página.
        """
        query = (
            LogAcesso.query
            .join(Usuario, Usuario.id == LogAcesso.id_usuario)
            .filter(LogAcesso.id_empresa == id_empresa, Usuario.uuid == uuid_usuario)
        )
        if operacao:
            query = query.filter(LogAcesso.operacao == operacao)
        query = _filtrar_periodo(query, LogAcesso.data_hora, data_inicio, data_fim)
        query = _filtrar_cursor(query, LogAcesso.data_hora, LogAcesso.uuid, cursor_data, cursor_uuid)

        return _paginar_cursor(query, LogAcesso.data_hora, LogAcesso.uuid, limit)

    def find_ultimo_por_usuarios(self, id_empresa: int, ids_usuario: List[int]) -> List[LogAcesso]:
        """Último log de acesso de cada usuário de `ids_usuario` (usado só para a página atual do resumo)."""
        return _ultimo_log_por_usuario(
            LogAcesso, LogAcesso.id_usuario, LogAcesso.data_hora, id_empresa, ids_usuario
        )


class LogAlteracaoRepository(IRepository[LogAlteracao]):

    def find_by_id(self, id: int) -> Optional[LogAlteracao]:
        return db.session.get(LogAlteracao, id)

    def find_by_uuid(self, uuid: str) -> Optional[LogAlteracao]:
        return LogAlteracao.query.filter_by(uuid=uuid).first()

    def find_por_registro(self, tabela_origem: str, uuid_registro: str,
                          id_empresa: int) -> List[LogAlteracao]:
        """Histórico completo de alterações de um registro, do mais recente ao mais antigo."""
        return LogAlteracao.query.filter_by(
            tabela_origem=tabela_origem, uuid_registro=uuid_registro,
            id_empresa=id_empresa,
        ).order_by(LogAlteracao.alterado_em.desc()).all()

    def save(self, entity: LogAlteracao) -> LogAlteracao:
        """Adiciona o log à sessão, sem commit (o commit fica com quem orquestra a transação)."""
        db.session.add(entity)
        return entity

    def delete(self, id: int) -> bool:
        """Sempre False: a trilha de auditoria é imutável por design."""
        return False

    def find_all(self, id_empresa: int, *, uuid_usuario: Optional[str] = None,
                 nome_usuario: Optional[str] = None, acao: Optional[str] = None,
                 operacao: Optional[str] = None,
                 data_inicio: Optional[datetime] = None, data_fim: Optional[datetime] = None,
                 page: int = 1, per_page: int = PER_PAGE_PADRAO) -> Tuple[List[LogAlteracao], int]:
        """Listagem filtrada e paginada (offset/limit), escopada por empresa. Retorna (itens, total).

        `operacao` é a categoria de negócio (mesmo vocabulário de LogAcesso),
        traduzida para INSERT/UPDATE/DELETE. Sem equivalente SQL (ex.:
        "leitura"), o filtro ainda é aplicado e o resultado é vazio, em vez de
        devolver tudo.
        """
        query = LogAlteracao.query.filter(LogAlteracao.id_empresa == id_empresa)
        query = _filtrar_usuario(query, LogAlteracao.alterado_por, uuid_usuario, nome_usuario)
        if acao:
            query = query.filter(LogAlteracao.acao == acao)
        query = self._filtrar_operacao(query, operacao)
        query = _filtrar_periodo(query, LogAlteracao.alterado_em, data_inicio, data_fim)

        return _paginar_offset(query, (LogAlteracao.alterado_em.desc(),), page, per_page)

    def find_por_usuario_cursor(self, uuid_usuario: str, id_empresa: int, *,
                                acao: Optional[str] = None, operacao: Optional[str] = None,
                                data_inicio: Optional[datetime] = None,
                                data_fim: Optional[datetime] = None,
                                cursor_data: Optional[datetime] = None,
                                cursor_uuid: Optional[str] = None,
                                limit: int = CURSOR_LIMIT_PADRAO) -> Tuple[List[LogAlteracao], bool]:
        """Histórico de alteração de UM profissional, paginado por cursor.

        Mesma lógica de LogAcessoRepository.find_por_usuario_cursor.
        `acao` segue a mesma regra do resumo: texto livre de LogAlteracao.acao
        OU operação SQL traduzida da categoria (ex.: "escrita").
        Retorna (itens, tem_mais).
        """
        query = (
            LogAlteracao.query
            .join(Usuario, Usuario.id == LogAlteracao.alterado_por)
            .filter(LogAlteracao.id_empresa == id_empresa, Usuario.uuid == uuid_usuario)
        )
        if acao:
            query = query.filter(_condicao_acao_alteracao(acao))
        query = self._filtrar_operacao(query, operacao)
        query = _filtrar_periodo(query, LogAlteracao.alterado_em, data_inicio, data_fim)
        query = _filtrar_cursor(query, LogAlteracao.alterado_em, LogAlteracao.uuid, cursor_data, cursor_uuid)

        return _paginar_cursor(query, LogAlteracao.alterado_em, LogAlteracao.uuid, limit)

    def find_ultimo_por_usuarios(self, id_empresa: int, ids_usuario: List[int]) -> List[LogAlteracao]:
        """Última alteração de cada usuário de `ids_usuario`."""
        return _ultimo_log_por_usuario(
            LogAlteracao, LogAlteracao.alterado_por, LogAlteracao.alterado_em, id_empresa, ids_usuario
        )

    @staticmethod
    def _filtrar_operacao(query, operacao: Optional[str]):
        """Aplica o filtro de operação traduzido para valores SQL, quando houver `operacao`."""
        operacoes_sql = _operacoes_sql_para_filtro(operacao)
        if operacoes_sql is not None:
            query = query.filter(LogAlteracao.operacao.in_(operacoes_sql))
        return query