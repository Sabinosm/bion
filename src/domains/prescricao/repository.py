"""
Repositórios do domínio Prescrição: ResultadoPrescricao (diagnóstico),
Prescricao (medicamentos) e PrescricaoExame.
"""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import ResultadoPrescricao, Prescricao
from src.models.clinico.prescricao_exame import PrescricaoExame


class ResultadoPrescricaoRepository(IRepository[ResultadoPrescricao]):
    """Encapsula todo acesso a dados de ResultadoPrescricao via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[ResultadoPrescricao]:
        """Busca um ResultadoPrescricao pelo ID interno (chave primária)."""
        return db.session.get(ResultadoPrescricao, id)

    def find_by_uuid(self, uuid: str) -> Optional[ResultadoPrescricao]:
        """Busca um ResultadoPrescricao pelo UUID público exposto na API."""
        return ResultadoPrescricao.query.filter_by(uuid=uuid).first()

    def find_por_atendimento(self, id_atendimento: int) -> List[ResultadoPrescricao]:
        """Lista os ResultadoPrescricao associados a um Atendimento."""
        return ResultadoPrescricao.query.filter_by(id_atendimento=id_atendimento).all()

    def save(self, entity: ResultadoPrescricao) -> ResultadoPrescricao:
        """Persiste (insert ou update) um ResultadoPrescricao e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove um ResultadoPrescricao pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[ResultadoPrescricao]:
        """Lista todos os ResultadoPrescricao cadastrados, sem filtro."""
        return ResultadoPrescricao.query.all()
    
    def top_cid_por_regiao(self, id_empresa: int, dias: int = 14, limite: int = 10):
            return self.repo.top_cid_por_regiao(id_empresa=id_empresa, dias=dias, limite=limite)
     
        # --- C3 (bônus): base para incidência por 100 mil ---
    def total_casos_por_regiao(self, id_empresa: int, dias: int = 14):
        return self.repo.total_casos_por_regiao(id_empresa=id_empresa, dias=dias)


class PrescricaoRepository(IRepository[Prescricao]):
    """Encapsula todo acesso a dados de Prescricao (medicamento) via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[Prescricao]:
        """Busca uma Prescricao pelo ID interno (chave primária)."""
        return db.session.get(Prescricao, id)

    def find_by_uuid(self, uuid: str) -> Optional[Prescricao]:
        """
        Prescricao não possui UUID próprio no schema original.

        TODO: avaliar se vale adicionar uuid a Prescricao para uso consistente
        com o restante da API, ou se deve permanecer acessível só via resultado.
        """
        return None

    def find_por_resultado(self, id_resultado_prescricao: int) -> List[Prescricao]:
        """Lista as Prescricao (medicamentos) de um ResultadoPrescricao."""
        return Prescricao.query.filter_by(id_resultado_prescricao=id_resultado_prescricao).all()

    def save(self, entity: Prescricao) -> Prescricao:
        """Persiste (insert ou update) uma Prescricao e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove uma Prescricao pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[Prescricao]:
        """Lista todas as Prescricao cadastradas, sem filtro."""
        return Prescricao.query.all()


class PrescricaoExameRepository(IRepository[PrescricaoExame]):
    """Encapsula todo acesso a dados de PrescricaoExame via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[PrescricaoExame]:
        """Busca um PrescricaoExame pelo ID interno (chave primária)."""
        return db.session.get(PrescricaoExame, id)

    def find_by_uuid(self, uuid: str) -> Optional[PrescricaoExame]:
        """Busca um PrescricaoExame pelo UUID público exposto na API."""
        return PrescricaoExame.query.filter_by(uuid=uuid).first()

    def find_por_resultado(self, id_resultado: int) -> List[PrescricaoExame]:
        """Lista os PrescricaoExame associados a um ResultadoPrescricao."""
        return PrescricaoExame.query.filter_by(id_resultado=id_resultado).all()

    def save(self, entity: PrescricaoExame) -> PrescricaoExame:
        """Persiste (insert ou update) um PrescricaoExame e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove um PrescricaoExame pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[PrescricaoExame]:
        """Lista todos os PrescricaoExame cadastrados, sem filtro."""
        return PrescricaoExame.query.all()
    
    # --- D3: Urgência de exames -- IA vs. profissional ---
    def urgencia_por_origem(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Contagem de PrescricaoExame cruzando urgencia x origem_sugestao,
        filtrado por empresa (via ResultadoPrescricao -> Atendimento ->
        realizado_por -> Usuario) e por janela de tempo.
 
        Retorna lista de dicts:
        [{"urgencia": "urgente", "origem_sugestao": "bion_ia", "total": 26}, ...]
        """
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.clinico import ResultadoPrescricao, Atendimento
 
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
 
        linhas = (
            db.session.query(
                PrescricaoExame.urgencia.label("urgencia"),
                PrescricaoExame.origem_sugestao.label("origem_sugestao"),
                func.count(PrescricaoExame.id).label("total"),
            )
            .join(ResultadoPrescricao, PrescricaoExame.id_resultado == ResultadoPrescricao.id)
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(PrescricaoExame.criado_em >= limite)
            .group_by(PrescricaoExame.urgencia, PrescricaoExame.origem_sugestao)
            .all()
        )
        return [
            {"urgencia": linha.urgencia, "origem_sugestao": linha.origem_sugestao, "total": linha.total}
            for linha in linhas
        ]
