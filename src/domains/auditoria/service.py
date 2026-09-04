"""
Regras de negocio do dominio Auditoria.

Os logs sao gravados de forma append-only (sem update/delete, ver
repository.py) para atender ao requisito de imutabilidade citado nas
memorias do projeto (trilha de auditoria LGPD).

Sobre transacao e commit
--------------------------
`registrar_acesso` e `registrar_alteracao` NAO commitam a transacao --
so adicionam a entidade a sessao (via repository.save(), que tambem
nao commita mais). Isso e proposital: para uma acao sensivel, o log
precisa entrar na MESMA transacao da alteracao que ele descreve, com
um commit() so no final (ver acao_sensivel.py).

Sobre id_empresa (bug de permissao corrigido)
------------------------------------------------
Todo metodo de LEITURA abaixo exige `id_empresa` explicitamente e o
repassa ao repository, que filtra por ele em toda query. Nenhuma
consulta atravessa tenant.

Sobre id_usuario x uuid_usuario (privacidade / nao vazar PK interna)
-------------------------------------------------------------------------
Nenhum metodo publico deste service aceita ou devolve `id_usuario`
(a PK interna, sequencial). Toda entrada/saida usa `uuid_usuario`. O
id interno so existe dentro do repository, nas queries de JOIN --
nunca cruza a fronteira service/controller. Isso vale tambem para os
UUIDs dos proprios logs (ja eram uuid desde o inicio) e agora tambem
para o usuario referenciado por eles.

Sobre paginacao
-------------------
- Resumo por profissional e listagens simples (/acessos, /alteracoes):
  offset/limit convencional, com `limit` maximo travado (ver
  repository.LIMIT_MAXIMO) para o front nao pedir paginas gigantes.
- Detalhe do profissional: cursor por data (keyset pagination). Offset
  pagina por POSICAO; com log em fluxo continuo (chegando em tempo
  real), isso desloca paginas e pode pular ou repetir itens entre uma
  chamada e outra. Cursor pagina pelo proprio valor de data_hora do
  ultimo item visto, o que e estavel independente de quantos logs
  novos cheguem entre as chamadas -- e, como o proprio filtro de
  periodo, e naturalmente "guiado por data".

Sobre `acao`
---------------
`acao` (ex: "editar_paciente", "visualizar_paciente") e texto livre
por enquanto, nao Enum -- o vocabulario ainda esta sendo definido
manualmente em cada uso de @acao_sensivel/@acesso_auditado.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from src.core.exceptions import RecursoNaoEncontradoError, PermissaoNegadaError, DadosInvalidosError
from .repository import (
    LogAcessoRepository, LogAlteracaoRepository, AuditoriaResumoRepository,
    PER_PAGE_PADRAO, LIMIT_MAXIMO, CURSOR_LIMIT_PADRAO,
)

# Janela maxima de consulta sem forcar paginacao curta -- alinhado com o
# limite de "ate 7 dias" citado no design da tela.
JANELA_MAXIMA_DIAS = 7


class AuditoriaService:

    def __init__(self):
        self.acesso_repo = LogAcessoRepository()
        self.alteracao_repo = LogAlteracaoRepository()
        self.resumo_repo = AuditoriaResumoRepository()

    # ------------------------------------------------------------------
    # Escrita (chamadas pelos decorators de acaoSensivel.py)
    # ------------------------------------------------------------------

    def registrar_acesso(self, id_empresa: int, id_usuario: int, recurso: str, operacao: str,
                          ip_origem: str, resultado: str = "sucesso", uuid_paciente: str = None):
        # id_usuario aqui e o id INTERNO, vindo de get_id_usuario_sessao()
        # (sessao autenticada) -- nunca do client. So a leitura/consulta
        # publica e restrita a uuid.
        from src.models.auditoria.log_acesso import LogAcesso
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

    def registrar_alteracao(self, id_empresa: int, tabela_origem: str, id_registro: int,
                             uuid_registro: str, operacao: str, acao: str = None,
                             id_usuario: int = None, campo_alterado: str = None,
                             valor_anterior: str = None, valor_novo: str = None,
                             ip_origem: str = None, justificativa: str = None):
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

    # ------------------------------------------------------------------
    # Leitura -- listagens simples (offset/limit)
    # ------------------------------------------------------------------

    def listar_acessos(self, id_empresa: int, *, uuid_usuario: str = None,
                        nome_usuario: str = None, operacao: str = None,
                        data_inicio: datetime = None, data_fim: datetime = None,
                        page: int = 1, limit: int = PER_PAGE_PADRAO):
        self._validar_periodo(data_inicio, data_fim)
        return self.acesso_repo.find_all(
            id_empresa, uuid_usuario=uuid_usuario, nome_usuario=nome_usuario,
            operacao=operacao, data_inicio=data_inicio, data_fim=data_fim,
            page=page, per_page=limit,
        )

    def listar_alteracoes(self, id_empresa: int, *, tabela_origem: str = None,
                           uuid_registro: str = None, uuid_usuario: str = None,
                           nome_usuario: str = None, acao: str = None, operacao: str = None,
                           data_inicio: datetime = None, data_fim: datetime = None,
                           page: int = 1, limit: int = PER_PAGE_PADRAO):
        if tabela_origem and uuid_registro:
            # Drill-down por registro alterado -- nao pagina.
            return self.alteracao_repo.find_por_registro(tabela_origem, uuid_registro, id_empresa)

        self._validar_periodo(data_inicio, data_fim)
        return self.alteracao_repo.find_all(
            id_empresa, uuid_usuario=uuid_usuario, nome_usuario=nome_usuario,
            acao=acao, operacao=operacao, data_inicio=data_inicio, data_fim=data_fim,
            page=page, per_page=limit,
        )

    # ------------------------------------------------------------------
    # Leitura -- resumo por profissional (tela principal, paginada e
    # ordenada por nome)
    # ------------------------------------------------------------------

    def listar_resumo_por_profissional(self, id_empresa: int, *, nome_usuario: str = None,
                                        tipo_usuario: str = None, acao: str = None,
                                        page: int = 1, limit: int = PER_PAGE_PADRAO):
        """Uma pagina de profissionais (ordem alfabetica, com pelo menos
        um log de acesso ou alteracao), cada um com seu ultimo acesso e
        ultima alteracao. O "ultimo evento" e buscado so para quem esta
        NESTA pagina (10-50 usuarios), nao para a empresa toda -- ponto
        importante de performance agora que o resumo pagina de verdade.
        """
        profissionais, total = self.resumo_repo.find_profissionais(
            id_empresa, nome_usuario=nome_usuario, tipo_usuario=tipo_usuario, acao=acao,
            page=page, per_page=limit,
        )

        ids_pagina = [p.id_usuario for p in profissionais]
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
            entrada = {"uuid_usuario": p.uuid, "nome": p.nome}
            if p.id_usuario in ultimos_acessos:
                entrada["ultimo_acesso"] = ultimos_acessos[p.id_usuario].to_dict_resumido()
            if p.id_usuario in ultimas_alteracoes:
                entrada["ultima_alteracao"] = ultimas_alteracoes[p.id_usuario].to_dict_resumido()
            itens.append(entrada)

        return itens, total

    # ------------------------------------------------------------------
    # Leitura -- detalhe do profissional (cursor por data)
    # ------------------------------------------------------------------

    def detalhe_profissional(self, id_empresa: int, uuid_usuario: str, *,
                              acao: str = None, operacao_acesso: str = None,
                              data_inicio: datetime = None, data_fim: datetime = None,
                              cursor_acessos: dict = None, cursor_alteracoes: dict = None,
                              limit: int = CURSOR_LIMIT_PADRAO):
        """Historico completo (acesso + alteracao) de um profissional,
        identificado por uuid. Cada bloco pagina por cursor de data,
        independente um do outro.

        `acao` e um filtro unico aplicado aos dois blocos: no bloco de
        acesso, bate contra LogAcesso.operacao (categoria fechada); no
        bloco de alteracao, bate contra LogAlteracao.acao (texto livre,
        ex: "editar_paciente") OU LogAlteracao.operacao traduzida (ex:
        "escrita" -> INSERT/UPDATE) -- ver _operacoes_sql_para_filtro no
        repository. Isso deixa o mesmo campo de filtro na UI cobrir os
        dois vocabularios sem o usuario precisar saber qual log usa qual.

        `operacao_acesso`: filtro adicional so para o bloco de acesso,
        quando o filtro por `acao` (mais amplo) nao for suficiente.

        cursor_acessos / cursor_alteracoes: dict {"data": datetime,
        "uuid": str} do ultimo item visto naquele bloco, ou None para
        comecar do mais recente. O client recebe esse par de volta em
        cada item (`data_hora`/`alterado_em` + `uuid`) e devolve como
        cursor na chamada seguinte para "carregar mais".
        """
        self._validar_periodo(data_inicio, data_fim)

        cursor_acessos = cursor_acessos or {}
        cursor_alteracoes = cursor_alteracoes or {}

        acessos, tem_mais_acessos = self.acesso_repo.find_por_usuario_cursor(
            uuid_usuario, id_empresa, operacao=(operacao_acesso or acao),
            data_inicio=data_inicio, data_fim=data_fim,
            cursor_data=cursor_acessos.get("data"), cursor_uuid=cursor_acessos.get("uuid"),
            limit=limit,
        )
        alteracoes, tem_mais_alteracoes = self.alteracao_repo.find_por_usuario_cursor(
            uuid_usuario, id_empresa, acao=acao, operacao=acao,
            data_inicio=data_inicio, data_fim=data_fim,
            cursor_data=cursor_alteracoes.get("data"), cursor_uuid=cursor_alteracoes.get("uuid"),
            limit=limit,
        )

        return {
            "acessos": {"itens": acessos, "tem_mais": tem_mais_acessos},
            "alteracoes": {"itens": alteracoes, "tem_mais": tem_mais_alteracoes},
        }

    def excluir(self, *args, **kwargs):
        raise PermissaoNegadaError("Registros de auditoria são imutáveis e não podem ser excluídos.")

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _validar_periodo(self, data_inicio: Optional[datetime], data_fim: Optional[datetime]):
        if data_inicio and data_fim and (data_fim - data_inicio) > timedelta(days=JANELA_MAXIMA_DIAS):
            raise DadosInvalidosError(
                f"Periodo maximo de consulta e {JANELA_MAXIMA_DIAS} dias. "
                f"Reduza o intervalo ou use paginacao."
            )