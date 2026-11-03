"""resultado_prescricao_repository.py

Acesso a dados do ResultadoPrescricao (diagnóstico CID-10, desfecho e status do
rascunho): busca por UUID dentro da empresa, listagem por atendimento, controle
de transação e as agregações de diagnósticos usadas pelas estatísticas (por
região, evolução temporal de um CID).

A posse da empresa vem da Consulta do atendimento (um dado que não muda), e não
do usuário que realizou, e as agregações contam só resultados CONFIRMADOS. A
transação segue o padrão dos demais repositórios: salvar, confirmar e desfazer,
com commit desligado só fazendo flush (o fluxo da IA grava tudo num commit
único no fim).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List

from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import ResultadoPrescricao, Atendimento, Consulta


class ResultadoPrescricaoRepository(IRepository[ResultadoPrescricao]):

    # ------------------------------------------------------------ transação
    def confirmar(self, commit: bool = True) -> None:
        """commit=True: commita; commit=False: só flush (a transação segue aberta)."""
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    # ---------------------------------------------------------------- leitura
    def find_by_id(self, id: int) -> Optional[ResultadoPrescricao]:
        return db.session.get(ResultadoPrescricao, id)

    def find_by_uuid(self, uuid: str) -> Optional[ResultadoPrescricao]:
        return ResultadoPrescricao.query.filter_by(uuid=uuid).first()

    def find_by_uuid_da_empresa(self, uuid: str, id_empresa: int) -> Optional[ResultadoPrescricao]:
        """Só devolve o resultado se o atendimento pertence a uma Consulta da empresa."""
        return (
            ResultadoPrescricao.query
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(ResultadoPrescricao.uuid == uuid, Consulta.id_empresa == id_empresa)
            .first()
        )

    def find_do_atendimento(self, id_atendimento: int) -> List[ResultadoPrescricao]:
        """Todos os resultados do atendimento (rascunho, confirmado e descartado), do mais antigo ao mais novo."""
        return (
            ResultadoPrescricao.query
            .filter(ResultadoPrescricao.id_atendimento == id_atendimento)
            .order_by(ResultadoPrescricao.criado_em.asc(), ResultadoPrescricao.id.asc())
            .all()
        )

    def find_all(self) -> List[ResultadoPrescricao]:
        return ResultadoPrescricao.query.all()

    # --------------------------------------------------------------- escrita
    def save(self, entity: ResultadoPrescricao, commit: bool = True) -> ResultadoPrescricao:
        """Persiste (insert ou update). commit=False só faz flush: gera ids sem fechar a transação."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        self.confirmar()
        return True

    # ------------------------------------------------------------ estatísticas
    @staticmethod
    def _confirmados_da_empresa(colunas: tuple, id_empresa: int, desde, ate=None):
        """Base das agregações: resultados confirmados formulados em [desde, ate) (sem `ate`, sem limite
        superior), das Consultas da empresa. Já junta Atendimento e Consulta."""
        consulta = (
            db.session.query(*colunas)
            .select_from(ResultadoPrescricao)
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Consulta.id_empresa == id_empresa)
            .filter(ResultadoPrescricao.data_hora_formulacao >= desde)
            .filter(ResultadoPrescricao.status == "confirmado")
        )
        if ate is not None:
            consulta = consulta.filter(ResultadoPrescricao.data_hora_formulacao < ate)
        return consulta

    def top_cid_por_regiao(self, id_empresa: int, dias: int = 14, limite: int = 10) -> List[dict]:
        """Ranking de CID10 mais diagnosticados, agrupado por região geográfica do PACIENTE (não da
        empresa: pacientes de uma mesma empresa/UBS podem vir de regiões diferentes).

        Caminho: ResultadoPrescricao -> Atendimento -> Consulta (empresa) -> Paciente -> RegiaoGeografica.

        Retorna: [{"codigo_cid10": "A90", "descricao_cid10": "Dengue",
                   "regiao": "Zona Leste", "id_regiao": 4, "total": 37}, ...]
        """
        from src.models.pacientes import Paciente
        from src.models.corp.regiao_geografica import RegiaoGeografica

        desde = datetime.now(timezone.utc) - timedelta(days=dias)
        linhas = (
            self._confirmados_da_empresa(
                (ResultadoPrescricao.codigo_cid10_principal.label("codigo_cid10"),
                 ResultadoPrescricao.descricao_cid10_principal.label("descricao_cid10"),
                 RegiaoGeografica.id.label("id_regiao"),
                 RegiaoGeografica.nome_regiao.label("regiao"),
                 func.count(ResultadoPrescricao.id).label("total")),
                id_empresa, desde,
            )
            .join(Paciente, Consulta.id_paciente == Paciente.id)
            .join(RegiaoGeografica, Paciente.id_regiao_geografica == RegiaoGeografica.id)
            .group_by(
                ResultadoPrescricao.codigo_cid10_principal,
                ResultadoPrescricao.descricao_cid10_principal,
                RegiaoGeografica.id,
                RegiaoGeografica.nome_regiao,
            )
            .order_by(func.count(ResultadoPrescricao.id).desc())
            .limit(limite)
            .all()
        )
        return [
            {
                "codigo_cid10": linha.codigo_cid10,
                "descricao_cid10": linha.descricao_cid10,
                "id_regiao": linha.id_regiao,
                "regiao": linha.regiao,
                "total": linha.total,
            }
            for linha in linhas
        ]

    def total_casos_por_regiao(self, id_empresa: int, dias: int = 14) -> List[dict]:
        """Total de diagnósticos (todos os CIDs juntos) por região, no período, com a população
        estimada da região. Base para a incidência por 100 mil: a divisão casos/população fica na
        camada de estatística, não aqui (o repository só agrega, não calcula taxa).

        Retorna: [{"id_regiao": 4, "regiao": "Zona Leste", "populacao_estimada": 250000, "total": 152}, ...]
        `populacao_estimada` é None quando a região não tem população cadastrada.
        """
        from src.models.pacientes import Paciente
        from src.models.corp.regiao_geografica import RegiaoGeografica

        desde = datetime.now(timezone.utc) - timedelta(days=dias)
        linhas = (
            self._confirmados_da_empresa(
                (RegiaoGeografica.id.label("id_regiao"),
                 RegiaoGeografica.nome_regiao.label("regiao"),
                 RegiaoGeografica.populacao_estimada.label("populacao_estimada"),
                 func.count(ResultadoPrescricao.id).label("total")),
                id_empresa, desde,
            )
            .join(Paciente, Consulta.id_paciente == Paciente.id)
            .join(RegiaoGeografica, Paciente.id_regiao_geografica == RegiaoGeografica.id)
            .group_by(
                RegiaoGeografica.id,
                RegiaoGeografica.nome_regiao,
                RegiaoGeografica.populacao_estimada,
            )
            .all()
        )
        return [
            {
                "id_regiao": linha.id_regiao,
                "regiao": linha.regiao,
                "populacao_estimada": linha.populacao_estimada,
                "total": linha.total,
            }
            for linha in linhas
        ]

    def _serie_diaria(self, id_empresa: int, codigo_cid10: str, desde, ate=None) -> List[dict]:
        """Série diária de casos confirmados de um CID10 em [desde, ate), do mais antigo ao mais recente."""
        dia = func.date(ResultadoPrescricao.data_hora_formulacao)
        linhas = (
            self._confirmados_da_empresa(
                (dia.label("data"), func.count(ResultadoPrescricao.id).label("total")),
                id_empresa, desde, ate,
            )
            .filter(ResultadoPrescricao.codigo_cid10_principal == codigo_cid10)
            .group_by(dia)
            .order_by(dia.asc())
            .all()
        )
        return [{"data": linha.data, "total": linha.total} for linha in linhas]

    def evolucao_cid(self, id_empresa: int, codigo_cid10: str, dias: int = 30) -> List[dict]:
        """Série diária de casos de 1 CID10 nos últimos `dias`, para gráfico de linha de tendência
        (ex.: acompanhar a curva de dengue ao longo do surto).

        Retorna: [{"data": date, "total": int}, ...] do mais antigo ao mais recente.
        """
        desde = datetime.now(timezone.utc) - timedelta(days=dias)
        return self._serie_diaria(id_empresa, codigo_cid10, desde)

    def evolucao_cid_periodo(self, id_empresa: int, codigo_cid10: str, data_inicio, data_fim) -> List[dict]:
        """Mesma série de `evolucao_cid`, com janela explícita [data_inicio, data_fim): usada para o
        total do período ANTERIOR na comparação."""
        return self._serie_diaria(id_empresa, codigo_cid10, data_inicio, data_fim)
