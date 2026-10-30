"""repository.py

Acesso a dados da entidade Atendimento via SQLAlchemy: busca por UUID dentro
da empresa, listagens por Consulta e por paciente, controle de transação e as
agregações usadas pelas estatísticas (tempo médio por tipo, contagem por
status, tempo entre sintoma e busca por atendimento).

O Atendimento não tem empresa própria: a posse vem da Consulta, então as buscas
pela API e as agregações estatísticas juntam a Consulta e filtram pela empresa
dela (um dado que não muda), e "não existe" e "é de outra empresa" dão o mesmo
resultado. Nada é apagado fisicamente: a remoção é lógica, por cancelamento.

A transação segue o padrão dos demais repositórios: salvar, confirmar e
desfazer; com commit desligado só se faz flush, para o service compor várias
escritas num único commit.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List

from sqlalchemy import func, text
from sqlalchemy.orm import contains_eager, joinedload

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import Atendimento, Consulta
from src.models.clinico.coleta_clinica import ColetaClinica


def _duracao_segundos():
    """Expressão SQL da duração do Atendimento em segundos (MySQL: não existe EXTRACT(EPOCH))."""
    return func.timestampdiff(text("SECOND"), Atendimento.data_hora_inicio, Atendimento.data_hora_fim)


class AtendimentoRepository(IRepository[Atendimento]):

    # ------------------------------------------------------------ transação
    def confirmar(self, commit: bool = True) -> None:
        """commit=True: commita; commit=False: só flush (a transação segue aberta)."""
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    def travar(self, atendimento: Atendimento) -> Atendimento:
        """Relê a linha com SELECT ... FOR UPDATE (a trava vale até commit/rollback).
        Usado onde se lê, altera e grava o JSON do binário ou se revalida o status."""
        db.session.refresh(atendimento, with_for_update=True)
        return atendimento

    # ---------------------------------------------------------------- leitura
    def find_by_id(self, id: int) -> Optional[Atendimento]:
        """Busca um Atendimento pelo ID interno (chave primária)."""
        return db.session.get(Atendimento, id)

    def find_by_uuid(self, uuid: str, id_empresa: int) -> Optional[Atendimento]:
        """Busca um Atendimento pelo UUID público, DENTRO da empresa.
        'Não existe' e 'é de outra empresa' dão o mesmo resultado (None)."""
        return (
            Atendimento.query
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Atendimento.uuid == uuid, Consulta.id_empresa == id_empresa)
            .first()
        )

    def find_por_consulta(self, id_consulta: int) -> List[Atendimento]:
        """Lista os Atendimentos de uma Consulta em ordem cronológica crescente, com o id como
        desempate (sincronizar_status_consulta depende dessa ordem para achar o último)."""
        return (
            Atendimento.query
            .filter_by(id_consulta=id_consulta)
            .order_by(Atendimento.data_hora_inicio.asc(), Atendimento.id.asc())
            .all()
        )

    def find_em_andamento_por_consultas(self, ids_consulta: List[int]) -> dict:
        """{id_consulta: Atendimento em andamento}, numa única query, para várias Consultas.
        Há no máximo um por Consulta (regra do service); ids sem atendimento em andamento ficam de fora."""
        if not ids_consulta:
            return {}
        linhas = (
            Atendimento.query
            .filter(Atendimento.id_consulta.in_(ids_consulta), Atendimento.status == "em-andamento")
            .all()
        )
        return {a.id_consulta: a for a in linhas}

    def find_anteriores_do_paciente(self, id_paciente: int, id_atendimento_atual: int,
                                    id_empresa: int, limite: int = 50) -> List[Atendimento]:
        """Atendimentos FINALIZADOS anteriores do paciente (de qualquer Consulta da empresa), do
        mais recente para o mais antigo. Só finalizado: o binário dele está completo e confirmado.
        Usado para derivar o binário do atendimento novo. ASSUME Consulta.id_paciente."""
        return (
            Atendimento.query
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(
                Consulta.id_empresa == id_empresa,
                Consulta.id_paciente == id_paciente,
                Atendimento.id != id_atendimento_atual,
                Atendimento.status == "finalizado",
            )
            .order_by(Atendimento.data_hora_inicio.desc(), Atendimento.id.desc())
            .limit(limite)
            .all()
        )

    def find_ultimo_por_tipo(self, id_consulta: int, tipo_atendimento: str) -> Optional[Atendimento]:
        """Atendimento mais recente de um tipo específico dentro de uma Consulta."""
        return (
            Atendimento.query
            .filter_by(id_consulta=id_consulta, tipo_atendimento=tipo_atendimento)
            .order_by(Atendimento.data_hora_inicio.desc(), Atendimento.id.desc())
            .first()
        )

    def find_all(self, id_empresa: int) -> List[Atendimento]:
        """Lista os Atendimentos da empresa, do mais recente para o mais antigo."""
        return (
            Atendimento.query
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .options(contains_eager(Atendimento.consulta), joinedload(Atendimento.usuario))
            .filter(Consulta.id_empresa == id_empresa)
            .order_by(Atendimento.data_hora_inicio.desc())
            .all()
        )

    # --------------------------------------------------------------- escrita
    def save(self, entity: Atendimento, commit: bool = True) -> Atendimento:
        """Persiste (insert ou update) um Atendimento. commit=False só faz flush."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError(
            "Atendimento não é apagado fisicamente; use cancelar (status='cancelado')."
        )

    # ------------------------------------------------------------ estatísticas
    @staticmethod
    def _agregar_tempo_medio_por_tipo(id_empresa: int, inicio, fim=None) -> List[dict]:
        """Duração média, em segundos, dos Atendimentos finalizados por tipo, para os que
        começaram em [inicio, fim) (sem `fim`, sem limite superior). Empresa pela Consulta."""
        duracao = _duracao_segundos()
        consulta = (
            db.session.query(
                Atendimento.tipo_atendimento.label("tipo_atendimento"),
                func.avg(duracao).label("media_segundos"),
                func.count(Atendimento.id).label("total"),
            )
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Consulta.id_empresa == id_empresa)
            .filter(Atendimento.data_hora_inicio >= inicio)
            .filter(Atendimento.data_hora_fim.isnot(None))
        )
        if fim is not None:
            consulta = consulta.filter(Atendimento.data_hora_inicio < fim)

        return [
            {
                "tipo_atendimento": linha.tipo_atendimento,
                "media_segundos": float(linha.media_segundos) if linha.media_segundos else 0.0,
                "total": linha.total,
            }
            for linha in consulta.group_by(Atendimento.tipo_atendimento).all()
        ]

    def tempo_medio_por_tipo(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Duração média de Atendimentos finalizados nos últimos `dias`, por tipo.

        Só considera atendimentos com data_hora_fim preenchida. Retorna
        [{"tipo_atendimento": "triagem", "media_segundos": 512.3, "total": 42}, ...].
        A conversão para texto e a variação % vs. período anterior ficam na camada de
        estatística; aqui só se agrega o dado bruto.
        """
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        return self._agregar_tempo_medio_por_tipo(id_empresa, limite)

    def tempo_medio_por_tipo_periodo(self, id_empresa: int, data_inicio, data_fim) -> List[dict]:
        """Mesma agregação de `tempo_medio_por_tipo`, com janela explícita [data_inicio, data_fim)
        em vez de 'últimos N dias', para comparar dois períodos que NÃO se sobrepõem."""
        return self._agregar_tempo_medio_por_tipo(id_empresa, data_inicio, data_fim)

    def contar_atendimentos_por_status(self, id_empresa: int, dias: int = 30) -> dict:
        """Contagem de Atendimentos por status ('em-andamento', 'finalizado', 'cancelado')
        nos últimos `dias`, no nível de Atendimento (e não de Consulta)."""
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        linhas = (
            db.session.query(
                Atendimento.status.label("status"),
                func.count(Atendimento.id).label("total"),
            )
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Consulta.id_empresa == id_empresa)
            .filter(Atendimento.data_hora_inicio >= limite)
            .group_by(Atendimento.status)
            .all()
        )
        return {linha.status: linha.total for linha in linhas}

    def media_horas_ate_atendimento(self, id_empresa: int, dias: int = 30) -> Optional[float]:
        """Média de desde_quando_sintomas (em horas) no período: quanto o paciente demora entre o
        início dos sintomas e a busca por atendimento. Só valores preenchidos; None se não há dados."""
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        media = (
            db.session.query(func.avg(ColetaClinica.desde_quando_sintomas))
            .join(Atendimento, ColetaClinica.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Consulta.id_empresa == id_empresa)
            .filter(Atendimento.data_hora_inicio >= limite)
            .filter(ColetaClinica.desde_quando_sintomas.isnot(None))
            .scalar()
        )
        return float(media) if media is not None else None

    def tempo_medio_por_tipo_segmentado(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Tempo médio por tipo (triagem e avaliação médica), quebrado em dois grupos por Consulta:
        'mesmo_profissional' (a triagem e a avaliação médica têm o mesmo realizado_por) e
        'transferencia' (profissionais diferentes). Sem essa distinção a média mistura dois
        comportamentos (o médico que faz a triagem sozinho tende a ser mais rápido que um
        enfermeiro dedicado) e enviesa o resultado.

        Consulta sem avaliação médica ainda não é classificável e fica de fora. Tudo (os grupos e a
        duração) é restrito às Consultas da empresa, para que dados de empresas diferentes não se misturem.
        Retorna [{"tipo_atendimento", "grupo", "media_segundos", "total"}, ...].
        """
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        duracao = _duracao_segundos()

        def _etapa(tipo: str):
            """realizado_por da etapa `tipo`, por consulta, só das Consultas da empresa."""
            return (
                db.session.query(
                    Atendimento.id_consulta.label("id_consulta"),
                    Atendimento.realizado_por.label("realizado_por"),
                )
                .join(Consulta, Atendimento.id_consulta == Consulta.id)
                .filter(Consulta.id_empresa == id_empresa, Atendimento.tipo_atendimento == tipo)
                .subquery()
            )

        triagens = _etapa("triagem")
        avaliacoes = _etapa("avaliacao-medica")

        mapa_grupo = (
            db.session.query(
                triagens.c.id_consulta,
                triagens.c.realizado_por.label("prof_triagem"),
                avaliacoes.c.realizado_por.label("prof_avaliacao"),
            )
            .outerjoin(avaliacoes, triagens.c.id_consulta == avaliacoes.c.id_consulta)
            .all()
        )
        grupo_por_consulta = {}
        for linha in mapa_grupo:
            if linha.prof_avaliacao is None:
                continue  # avaliação ainda não existe: não classificável
            grupo_por_consulta[linha.id_consulta] = (
                "mesmo_profissional" if linha.prof_triagem == linha.prof_avaliacao
                else "transferencia"
            )

        linhas = (
            db.session.query(
                Atendimento.id_consulta.label("id_consulta"),
                Atendimento.tipo_atendimento.label("tipo_atendimento"),
                duracao.label("duracao"),
            )
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Consulta.id_empresa == id_empresa)
            .filter(Atendimento.data_hora_inicio >= limite)
            .filter(Atendimento.data_hora_fim.isnot(None))
            .filter(Atendimento.tipo_atendimento.in_(["triagem", "avaliacao-medica"]))
            .all()
        )

        acumulado = {}  # (tipo, grupo) -> [soma, total]
        for linha in linhas:
            grupo = grupo_por_consulta.get(linha.id_consulta)
            if grupo is None:
                continue
            soma_total = acumulado.setdefault((linha.tipo_atendimento, grupo), [0.0, 0])
            soma_total[0] += float(linha.duracao or 0)
            soma_total[1] += 1

        return [
            {
                "tipo_atendimento": tipo,
                "grupo": grupo,
                "media_segundos": soma / total if total else 0.0,
                "total": total,
            }
            for (tipo, grupo), (soma, total) in acumulado.items()
        ]
