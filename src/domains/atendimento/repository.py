"""Repositório de acesso a dados da entidade Atendimento."""

from datetime import datetime, timedelta, timezone
from typing import Optional, List

from sqlalchemy import func, text

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import Atendimento


class AtendimentoRepository(IRepository[Atendimento]):
    """Encapsula todo acesso a dados de Atendimento via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[Atendimento]:
        """Busca um Atendimento pelo ID interno (chave primária)."""
        return db.session.get(Atendimento, id)

    def find_by_uuid(self, uuid: str) -> Optional[Atendimento]:
        """Busca um Atendimento pelo UUID público exposto na API."""
        return Atendimento.query.filter_by(uuid=uuid).first()

    def find_por_consulta(self, id_consulta: int) -> List[Atendimento]:
        """Lista os Atendimentos de uma Consulta, em ordem cronológica."""
        return (
            Atendimento.query
            .filter_by(id_consulta=id_consulta)
            .order_by(Atendimento.data_hora_inicio.asc())
            .all()
        )

    def find_ultimo_por_tipo(self, id_consulta: int, tipo_atendimento: str) -> Optional[Atendimento]:
        """Retorna o Atendimento mais recente de um tipo específico dentro de uma Consulta."""
        return (
            Atendimento.query
            .filter_by(id_consulta=id_consulta, tipo_atendimento=tipo_atendimento)
            .order_by(Atendimento.data_hora_inicio.desc())
            .first()
        )

    def save(self, entity: Atendimento) -> Atendimento:
        """Persiste (insert ou update) um Atendimento e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove um Atendimento pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[Atendimento]:
        """Lista todos os Atendimentos cadastrados, sem filtro."""
        return Atendimento.query.all()

    # --- A2: Tempo médio de atendimento, por tipo_atendimento ---
    # --- A2: Tempo médio de atendimento, por tipo_atendimento ---
    def tempo_medio_por_tipo(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Duração média de Atendimentos finalizados, agrupado por tipo.

        Só considera atendimentos com data_hora_fim preenchida (senão a
        duração não existe ainda). Filtra por empresa via o usuário que
        realizou o atendimento (realizado_por).

        Retorna lista de dicts:
        [{"tipo_atendimento": "triagem", "media_segundos": 512.3, "total": 42}, ...]

        A conversão para "8min32s" e o cálculo de variação % vs. período
        anterior ficam na camada de estatística (EstatisticasAtendimento),
        não aqui -- este método só agrega o dado bruto.
        """
        from src.models.usuarios.usuario import Usuario

        limite = datetime.now(timezone.utc) - timedelta(days=dias)

        # MySQL: TIMESTAMPDIFF(SECOND, inicio, fim) -- não existe EXTRACT(EPOCH)
        duracao_segundos = func.timestampdiff(
            text("SECOND"), Atendimento.data_hora_inicio, Atendimento.data_hora_fim
        )

        linhas = (
            db.session.query(
                Atendimento.tipo_atendimento.label("tipo_atendimento"),
                func.avg(duracao_segundos).label("media_segundos"),
                func.count(Atendimento.id).label("total"),
            )
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(Atendimento.data_hora_inicio >= limite)
            .filter(Atendimento.data_hora_fim.isnot(None))
            .group_by(Atendimento.tipo_atendimento)
            .all()
        )
        return [
            {
                "tipo_atendimento": linha.tipo_atendimento,
                "media_segundos": float(linha.media_segundos) if linha.media_segundos else 0.0,
                "total": linha.total,
            }
            for linha in linhas
        ]

    # --- Auxiliar para A3-equivalente no nível de Atendimento, se precisar ---
    def contar_atendimentos_por_status(self, id_empresa: int, dias: int = 30) -> dict:
        """Contagem de Atendimentos por status ('em-andamento', 'finalizado',
        'cancelado'), nos últimos N dias. Mesmo padrão de
        ConsultaRepository.contar_consultas_por_status, mas no nível de
        Atendimento -- útil se algum dia quiserem taxa de conclusão por
        etapa, não só por consulta inteira.
        """
        from src.models.usuarios.usuario import Usuario

        limite = datetime.now(timezone.utc) - timedelta(days=dias)

        linhas = (
            db.session.query(
                Atendimento.status.label("status"),
                func.count(Atendimento.id).label("total"),
            )
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(Atendimento.data_hora_inicio >= limite)
            .group_by(Atendimento.status)
            .all()
        )
        return {linha.status: linha.total for linha in linhas}