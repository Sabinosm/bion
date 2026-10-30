"""
service.py

Regras de negócio do domínio de Auditoria: gravação e consulta da trilha de
logs de acesso e de alteração de dados (requisito de rastreabilidade da LGPD).

Princípios do módulo:

- Imutabilidade: os logs são append-only. Não há atualização nem exclusão, e
  qualquer tentativa de exclusão é recusada.
- Transação: a gravação apenas adiciona o log à sessão, sem commit. Assim o
  log entra na mesma transação da ação que ele descreve, e quem orquestra
  (os decorators de ação sensível) faz um único commit no final.
- Isolamento por empresa: toda consulta exige o id da empresa e o repassa ao
  repository, que o aplica em todas as queries. Nada atravessa tenant.
- Privacidade: nenhuma entrada ou saída pública usa o id interno (sequencial)
  do usuário, apenas o uuid. O id interno existe só dentro do repository e na
  gravação, onde vem da sessão autenticada, nunca do client.
- Paginação: listagens simples usam offset/limit, com limite máximo travado no
  repository. O detalhe de um profissional usa cursor por data (keyset), que
  continua estável mesmo com logs novos chegando entre uma página e outra,
  coisa que offset não garante.
- Período: as consultas por data trabalham com janela máxima de 7 dias. Se
  só uma das pontas for informada, a outra é completada para fechar a janela;
  sem nenhuma, vale a janela dos últimos 7 dias.
- Deduplicação: leitura com sucesso do mesmo usuário, recurso e paciente dentro de
  JANELA_DEDUP_LEITURA_MIN (20 min) gera uma linha só. Escrita, exportação e negação
  nunca são deduplicadas.
- Ação: o campo `acao` é texto livre por enquanto, pois o vocabulário ainda
  está sendo definido a cada uso dos decorators.
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from src.core.exceptions import PermissaoNegadaError, DadosInvalidosError
from src.models import db
from .repository import (
    LogAcessoRepository, LogAlteracaoRepository, AuditoriaResumoRepository,
    PER_PAGE_PADRAO, CURSOR_LIMIT_PADRAO,
)

# Janela máxima de consulta, alinhada ao limite de 7 dias da tela.
JANELA_MAXIMA_DIAS = 7

# Janela de deduplicação de leituras (minutos). 0 desliga. Configurável por ambiente.
JANELA_DEDUP_LEITURA_MIN = int(os.getenv("AUDITORIA_JANELA_DEDUP_MIN", "20"))


class AuditoriaService:

    def __init__(self):
        self.acesso_repo = LogAcessoRepository()
        self.alteracao_repo = LogAlteracaoRepository()
        self.resumo_repo = AuditoriaResumoRepository()

    # ------------------------------------------------------------------
    # Escrita (chamada pelos decorators de acaoSensivel.py; sem commit)
    # ------------------------------------------------------------------

    def registrar_acesso(self, id_empresa: int, id_usuario: int, recurso: str, operacao: str,
                         ip_origem: str, uuid_paciente: Optional[str] = None,
                         resultado: str = "sucesso"):
        """Adiciona um log de acesso à sessão (sem commit).

        `id_usuario` é o id interno, vindo da sessão autenticada.
        `resultado` deve ser um valor válido do Enum de LogAcesso.resultado
        (sucesso, falha-autenticacao, acesso-negado, timeout).

        Leitura com sucesso repetida dentro da janela de deduplicação não grava nada
        e devolve None.
        """
        from src.models.auditoria.log_acesso import LogAcesso
        if operacao == "leitura" and resultado == "sucesso" and self._leitura_recente(
                LogAcesso, id_empresa, id_usuario, recurso, uuid_paciente):
            return None
        log = LogAcesso(
            id_empresa=id_empresa,
            id_usuario=id_usuario,
            recurso_acessado=recurso,
            operacao=operacao,
            data_hora=datetime.now(timezone.utc),
            ip_origem=ip_origem,
            resultado=resultado,
            uuid_paciente=uuid_paciente,
        )
        return self.acesso_repo.save(log)

    def registrar_acesso_negado(self, id_empresa: int, id_usuario: int, recurso: str, operacao: str,
                                ip_origem: str, motivo: str):
        """Adiciona à sessão um log de acesso com resultado "acesso-negado" e o motivo (sem commit)."""
        from src.models.auditoria.log_acesso import LogAcesso
        log = LogAcesso(
            id_empresa=id_empresa,
            id_usuario=id_usuario,
            recurso_acessado=recurso,
            operacao=operacao,
            data_hora=datetime.now(timezone.utc),
            ip_origem=ip_origem,
            resultado="acesso-negado",
            motivo_negacao=motivo,
        )
        return self.acesso_repo.save(log)

    def registrar_alteracao(self, id_empresa: int, tabela_origem: str, id_registro: int,
                            uuid_registro: str, operacao: str, acao: Optional[str] = None,
                            id_usuario: Optional[int] = None, campo_alterado: Optional[str] = None,
                            valor_anterior: Optional[str] = None, valor_novo: Optional[str] = None,
                            ip_origem: Optional[str] = None, justificativa: Optional[str] = None):
        """Adiciona um log de alteração de dados à sessão (sem commit).

        `operacao` é o valor estrutural do SQL (INSERT, UPDATE ou DELETE).
        Exclusões (DELETE) exigem `justificativa`; sem ela levanta DadosInvalidosError.
        """
        if operacao == "DELETE" and not justificativa:
            raise DadosInvalidosError(
                "Justificativa e obrigatoria para operacoes de exclusao (DELETE)."
            )

        from src.models.auditoria.log_alteracao import LogAlteracao
        log = LogAlteracao(
            id_empresa=id_empresa,
            acao=acao,
            tabela_origem=tabela_origem,
            id_registro=id_registro,
            uuid_registro=uuid_registro,
            operacao=operacao,
            campo_alterado=campo_alterado,
            valor_anterior=valor_anterior,
            valor_novo=valor_novo,
            alterado_por=id_usuario,
            ip_origem=ip_origem,
            justificativa=justificativa,
        )
        return self.alteracao_repo.save(log)

    def excluir(self, *args, **kwargs):
        """Sempre recusa: registros de auditoria são imutáveis."""
        raise PermissaoNegadaError("Registros de auditoria são imutáveis e não podem ser excluídos.")

    # ------------------------------------------------------------------
    # Leitura: listagens simples (offset/limit)
    # ------------------------------------------------------------------

    def listar_acessos(self, id_empresa: int, *, uuid_usuario: Optional[str] = None,
                       nome_usuario: Optional[str] = None, operacao: Optional[str] = None,
                       data_inicio: Optional[datetime] = None, data_fim: Optional[datetime] = None,
                       page: int = 1, limit: int = PER_PAGE_PADRAO):
        """Lista logs de acesso da empresa. Retorna (itens, total)."""
        data_inicio, data_fim = self._resolver_periodo(data_inicio, data_fim)
        return self.acesso_repo.find_all(
            id_empresa, uuid_usuario=uuid_usuario, nome_usuario=nome_usuario,
            operacao=operacao, data_inicio=data_inicio, data_fim=data_fim,
            page=page, per_page=limit,
        )

    def listar_alteracoes(self, id_empresa: int, *, tabela_origem: Optional[str] = None,
                          uuid_registro: Optional[str] = None, uuid_usuario: Optional[str] = None,
                          nome_usuario: Optional[str] = None, acao: Optional[str] = None,
                          operacao: Optional[str] = None,
                          data_inicio: Optional[datetime] = None, data_fim: Optional[datetime] = None,
                          page: int = 1, limit: int = PER_PAGE_PADRAO):
        """Lista logs de alteração da empresa.

        Se `tabela_origem` e `uuid_registro` forem informados, faz o drill-down
        do registro e retorna a lista completa, sem paginação e ignorando os
        demais filtros. Caso contrário retorna (itens, total).
        """
        if tabela_origem and uuid_registro:
            return self.alteracao_repo.find_por_registro(tabela_origem, uuid_registro, id_empresa)

        data_inicio, data_fim = self._resolver_periodo(data_inicio, data_fim)
        return self.alteracao_repo.find_all(
            id_empresa, uuid_usuario=uuid_usuario, nome_usuario=nome_usuario,
            acao=acao, operacao=operacao, data_inicio=data_inicio, data_fim=data_fim,
            page=page, per_page=limit,
        )

    # ------------------------------------------------------------------
    # Leitura: resumo por profissional (tela principal)
    # ------------------------------------------------------------------

    def listar_resumo_por_profissional(self, id_empresa: int, *, nome_usuario: Optional[str] = None,
                                       funcao_clinica: Optional[str] = None,
                                       is_admin: Optional[bool] = None, acao: Optional[str] = None,
                                       page: int = 1, limit: int = PER_PAGE_PADRAO):
        """Uma página de profissionais em ordem alfabética, cada um com o último acesso e a última alteração.

        Só entram profissionais com ao menos um log de acesso ou de alteração.
        O "último evento" é buscado apenas para quem está na página atual, e
        não para a empresa toda.

        `funcao_clinica` ("medico"/"enfermeiro") e `is_admin` são filtros
        independentes e combináveis; None significa não filtrar naquele eixo.

        Returns:
            (itens, total), onde cada item tem uuid_usuario, nome e,
            quando existirem, ultimo_acesso e ultima_alteracao.
        """
        profissionais, total = self.resumo_repo.find_profissionais(
            id_empresa, nome_usuario=nome_usuario, funcao_clinica=funcao_clinica,
            is_admin=is_admin, acao=acao, page=page, per_page=limit,
        )

        # Usuario tem PK `id`; `id_usuario` só existe nas tabelas de log.
        ids_pagina = [p.id for p in profissionais]
        ultimos_acessos = {
            log.id_usuario: log
            for log in self.acesso_repo.find_ultimo_por_usuarios(id_empresa, ids_pagina)
        }
        ultimas_alteracoes = {
            log.alterado_por: log
            for log in self.alteracao_repo.find_ultimo_por_usuarios(id_empresa, ids_pagina)
        }

        itens = []
        for p in profissionais:
            entrada = {"uuid_usuario": p.uuid, "nome": p.nome_completo}
            if p.id in ultimos_acessos:
                entrada["ultimo_acesso"] = ultimos_acessos[p.id].to_dict_resumido()
            if p.id in ultimas_alteracoes:
                entrada["ultima_alteracao"] = ultimas_alteracoes[p.id].to_dict_resumido()
            itens.append(entrada)

        return itens, total

    # ------------------------------------------------------------------
    # Leitura: detalhe do profissional (cursor por data)
    # ------------------------------------------------------------------

    def detalhe_profissional(self, id_empresa: int, uuid_usuario: str, *,
                             acao: Optional[str] = None, operacao_acesso: Optional[str] = None,
                             data_inicio: Optional[datetime] = None,
                             data_fim: Optional[datetime] = None,
                             cursor_acessos: Optional[dict] = None,
                             cursor_alteracoes: Optional[dict] = None,
                             limit: int = CURSOR_LIMIT_PADRAO):
        """Histórico completo (acessos e alterações) de um profissional, identificado por uuid.

        Cada bloco pagina por cursor de data, independente do outro.

        Args:
            acao: filtro aplicado aos dois blocos, com a mesma regra do resumo.
                No bloco de acessos compara com LogAcesso.operacao (categoria
                fechada); no de alterações, com LogAlteracao.acao (texto livre,
                ex.: "editar_paciente") OU com a operação SQL traduzida da
                categoria (ex.: "escrita" = INSERT/UPDATE).
            operacao_acesso: filtro extra, só do bloco de acessos; tem
                precedência sobre `acao` nesse bloco.
            cursor_acessos / cursor_alteracoes: {"data": datetime, "uuid": str}
                do último item visto no bloco, ou None para começar do mais
                recente.

        Returns:
            {"acessos": {"itens", "tem_mais"}, "alteracoes": {"itens", "tem_mais"}}
        """
        data_inicio, data_fim = self._resolver_periodo(data_inicio, data_fim)

        cursor_acessos = cursor_acessos or {}
        cursor_alteracoes = cursor_alteracoes or {}

        acessos, tem_mais_acessos = self.acesso_repo.find_por_usuario_cursor(
            uuid_usuario, id_empresa, operacao=(operacao_acesso or acao),
            data_inicio=data_inicio, data_fim=data_fim,
            cursor_data=cursor_acessos.get("data"), cursor_uuid=cursor_acessos.get("uuid"),
            limit=limit,
        )
        # `operacao` não é repassado de propósito: o repository já combina texto livre
        # e categoria traduzida (OR) a partir de `acao`; repassar `operacao=acao` como
        # filtro obrigatório esvaziaria o bloco para ações em texto livre.
        alteracoes, tem_mais_alteracoes = self.alteracao_repo.find_por_usuario_cursor(
            uuid_usuario, id_empresa, acao=acao,
            data_inicio=data_inicio, data_fim=data_fim,
            cursor_data=cursor_alteracoes.get("data"), cursor_uuid=cursor_alteracoes.get("uuid"),
            limit=limit,
        )

        return {
            "acessos": {"itens": acessos, "tem_mais": tem_mais_acessos},
            "alteracoes": {"itens": alteracoes, "tem_mais": tem_mais_alteracoes},
        }

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    @staticmethod
    def _leitura_recente(LogAcesso, id_empresa, id_usuario, recurso, uuid_paciente) -> bool:
        """True se já existe log de leitura bem-sucedida igual dentro da janela de deduplicação."""
        if JANELA_DEDUP_LEITURA_MIN <= 0:
            return False
        limite = datetime.now(timezone.utc) - timedelta(minutes=JANELA_DEDUP_LEITURA_MIN)
        existente = (
            db.session.query(LogAcesso.data_hora)
            .filter(
                LogAcesso.id_empresa == id_empresa,
                LogAcesso.id_usuario == id_usuario,
                LogAcesso.recurso_acessado == recurso,
                LogAcesso.operacao == "leitura",
                LogAcesso.resultado == "sucesso",
                LogAcesso.uuid_paciente == uuid_paciente,
                LogAcesso.data_hora >= limite,
            )
            .limit(1)
            .first()
        )
        return existente is not None

    @staticmethod
    def _resolver_periodo(data_inicio: Optional[datetime],
                          data_fim: Optional[datetime]) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Valida o período e completa a ponta que faltar, mantendo a janela de JANELA_MAXIMA_DIAS.

        - Só `data_inicio`: `data_fim` vira data_inicio + 7 dias.
        - Só `data_fim`: `data_inicio` vira data_fim - 7 dias.
        - Nenhuma das duas: últimos 7 dias (data_fim = agora em UTC).
        - Ambas: valida data_fim >= data_inicio e intervalo <= 7 dias.

        Raises:
            DadosInvalidosError: se data_fim for anterior a data_inicio ou o intervalo passar da janela.

        Returns:
            (data_inicio, data_fim) sempre preenchidos, para repassar ao repository.
        """
        janela = timedelta(days=JANELA_MAXIMA_DIAS)

        if data_inicio and data_fim:
            if data_fim < data_inicio:
                raise DadosInvalidosError("data_fim nao pode ser anterior a data_inicio.")
            if (data_fim - data_inicio) > janela:
                raise DadosInvalidosError(
                    f"Periodo maximo de consulta e {JANELA_MAXIMA_DIAS} dias. "
                    f"Reduza o intervalo ou use paginacao."
                )
        elif data_inicio:
            data_fim = data_inicio + janela
        elif data_fim:
            data_inicio = data_fim - janela
        else:
            data_fim = datetime.now(timezone.utc)
            data_inicio = data_fim - janela

        return data_inicio, data_fim