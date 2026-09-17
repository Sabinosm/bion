"""Repositório de acesso a dados da entidade ResultadoPrescricao."""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import ResultadoPrescricao


class ResultadoPrescricaoRepository(IRepository[ResultadoPrescricao]):

    def find_by_id(self, id: int) -> Optional[ResultadoPrescricao]:
        return db.session.get(ResultadoPrescricao, id)

    def find_by_uuid(self, uuid: str) -> Optional[ResultadoPrescricao]:
        return ResultadoPrescricao.query.filter_by(uuid=uuid).first()

    def save(self, entity: ResultadoPrescricao) -> ResultadoPrescricao:
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

    def find_all(self) -> List[ResultadoPrescricao]:
        return ResultadoPrescricao.query.all()

    # --- C1: Doenças mais comuns por região ---
    def top_cid_por_regiao(self, id_empresa: int, dias: int = 14, limite: int = 10) -> List[dict]:
        """Ranking de CID10 mais diagnosticados, agrupado por região
        geográfica do PACIENTE (não da empresa -- pacientes de uma
        mesma empresa/UBS podem vir de regiões diferentes).

        Caminho: ResultadoPrescricao -> Atendimento -> Consulta ->
        Paciente -> RegiaoGeografica. Filtra empresa via
        Atendimento.realizado_por -> Usuario.

        Retorna lista de dicts:
        [{"codigo_cid10": "A90", "descricao_cid10": "Dengue",
          "regiao": "Zona Leste", "id_regiao": 4, "total": 37}, ...]
        """
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.clinico import Atendimento, Consulta
        from src.models.pacientes import Paciente
        from src.models.corp.regiao_geografica import RegiaoGeografica

        limite_data = datetime.now(timezone.utc) - timedelta(days=dias)

        linhas = (
            db.session.query(
                ResultadoPrescricao.codigo_cid10_principal.label("codigo_cid10"),
                ResultadoPrescricao.descricao_cid10_principal.label("descricao_cid10"),
                RegiaoGeografica.id.label("id_regiao"),
                RegiaoGeografica.nome_regiao.label("regiao"),
                func.count(ResultadoPrescricao.id).label("total"),
            )
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .join(Paciente, Consulta.id_paciente == Paciente.id)
            .join(RegiaoGeografica, Paciente.id_regiao_geografica == RegiaoGeografica.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(ResultadoPrescricao.data_hora_formulacao >= limite_data)
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

    # --- C3 (bônus): base para incidência por 100 mil -- casos por região, sem GROUP BY CID ---
    def total_casos_por_regiao(self, id_empresa: int, dias: int = 14) -> List[dict]:
        """Total de diagnósticos (todos os CIDs juntos) por região, no
        período. Serve de numerador para C3 -- a divisão por
        RegiaoGeografica.populacao_estimada fica na camada de
        estatística, não aqui (repository só agrega, não calcula taxa).

        Retorna: [{"id_regiao": 4, "regiao": "Zona Leste", "total": 152}, ...]
        """
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.clinico import Atendimento, Consulta
        from src.models.pacientes import Paciente
        from src.models.corp.regiao_geografica import RegiaoGeografica

        limite_data = datetime.now(timezone.utc) - timedelta(days=dias)

        linhas = (
            db.session.query(
                RegiaoGeografica.id.label("id_regiao"),
                RegiaoGeografica.nome_regiao.label("regiao"),
                func.count(ResultadoPrescricao.id).label("total"),
            )
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .join(Paciente, Consulta.id_paciente == Paciente.id)
            .join(RegiaoGeografica, Paciente.id_regiao_geografica == RegiaoGeografica.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(ResultadoPrescricao.data_hora_formulacao >= limite_data)
            .group_by(RegiaoGeografica.id, RegiaoGeografica.nome_regiao)
            .all()
        )
        return [{"id_regiao": l.id_regiao, "regiao": l.regiao, "total": l.total} for l in linhas]

    # --- C2: Evolução temporal de um CID específico ---
    def evolucao_cid(self, id_empresa: int, codigo_cid10: str, dias: int = 30) -> List[dict]:
        """Série diária de casos de 1 CID10 específico, para gráfico de
        linha de tendência (ex: acompanhar curva de dengue ao longo do
        surto).

        Retorna: [{"data": date, "total": int}, ...] ordenado do mais
        antigo pro mais recente.
        """
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.clinico import Atendimento

        limite_data = datetime.now(timezone.utc) - timedelta(days=dias)
        dia = func.date(ResultadoPrescricao.data_hora_formulacao)

        linhas = (
            db.session.query(dia.label("data"), func.count(ResultadoPrescricao.id).label("total"))
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(ResultadoPrescricao.codigo_cid10_principal == codigo_cid10)
            .filter(ResultadoPrescricao.data_hora_formulacao >= limite_data)
            .group_by(dia)
            .order_by(dia.asc())
            .all()
        )
        return [{"data": linha.data, "total": linha.total} for linha in linhas]

    # --- C2 (comparação): evolução de 1 CID, com janela explícita ---
    def evolucao_cid_periodo(self, id_empresa: int, codigo_cid10: str, data_inicio, data_fim) -> List[dict]:
        """Mesma agregação de evolucao_cid, mas com data_inicio/data_fim
        explícitos -- usado para o total do período ANTERIOR na
        comparação de C2.
        """
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.clinico import Atendimento

        dia = func.date(ResultadoPrescricao.data_hora_formulacao)

        linhas = (
            db.session.query(dia.label("data"), func.count(ResultadoPrescricao.id).label("total"))
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(ResultadoPrescricao.codigo_cid10_principal == codigo_cid10)
            .filter(ResultadoPrescricao.data_hora_formulacao >= data_inicio)
            .filter(ResultadoPrescricao.data_hora_formulacao < data_fim)
            .group_by(dia)
            .order_by(dia.asc())
            .all()
        )
        return [{"data": linha.data, "total": linha.total} for linha in linhas]