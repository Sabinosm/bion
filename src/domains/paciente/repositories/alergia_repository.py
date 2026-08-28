from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (Alergia)



class AlergiaRepository(IRepository[Alergia]):

    def find_by_id(self, id: int) -> Optional[Alergia]:
        return db.session.get(Alergia, id)

    def find_by_uuid(self, uuid: str) -> Optional[Alergia]:
        return Alergia.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Alergia]:
        return Alergia.query.filter_by(id_paciente=id_paciente).all()

    def save(self, entity: Alergia) -> Alergia:
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

    def delete_by_uuid(self, uuid: str) -> bool:
        """Remove a alergia E suas reações associadas (cascade="all,
        delete-orphan" já configurado em Alergia.reacoes) -- forma mais
        comum de chamar isso a partir de uma rota HTTP."""
        e = self.find_by_uuid(uuid)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

     # --- A2: Tempo médio de atendimento, por tipo ---
    def tempo_medio_por_tipo(self, id_empresa: int, dias: int = 30):
        """Repassa a agregação bruta do repository (segundos, por tipo).
        Conversão para 'Xmin Ys' e variação % vs. período anterior ficam
        na camada de estatística."""
        return self.repo.tempo_medio_por_tipo(id_empresa=id_empresa, dias=dias)
 
    # --- auxiliar: status no nível de etapa (não usado na Fase 1, mas pronto) ---
    def atendimentos_por_status(self, id_empresa: int, dias: int = 30):
        return self.repo.contar_atendimentos_por_status(id_empresa=id_empresa, dias=dias)
 
    # --- E2: tempo médio por tipo, com janela explícita ---
    def tempo_medio_por_tipo_periodo(self, id_empresa: int, data_inicio, data_fim):
        return self.repo.tempo_medio_por_tipo_periodo(
            id_empresa=id_empresa, data_inicio=data_inicio, data_fim=data_fim
        )
        
    # --- F4: Gravidade geral das reações alérgicas (sem filtro por substância) ---
    def gravidade_geral(self, id_empresa: int) -> dict:
        """Mesma lógica de gravidade_por_substancia, mas sem o filtro
        WHERE substancia=... -- visão agregada de todas as reações da
        empresa, não drill-down de 1 substância específica.

        Retorna: {"leve": 30, "moderada": 45, "grave": 9}
        """
        from src.models import db
        from sqlalchemy import func

        from src.models.pacientes import Paciente
        from src.models.pacientes.reacao_alergia import ReacaoAlergia

        linhas = (
            db.session.query(
                    ReacaoAlergia.gravidade.label("gravidade"),
                    func.count(ReacaoAlergia.id).label("total"),
                )
                .join(Alergia, ReacaoAlergia.id_alergia == Alergia.id)
                .join(Paciente, Alergia.id_paciente == Paciente.id)
                .filter(Paciente.id_empresa == id_empresa)
                .group_by(ReacaoAlergia.gravidade)
                .all()
        )
        return {linha.gravidade: linha.total for linha in linhas}
    
    
    # --- D2: Alergias mais reportadas (por substância) ---
    def top_substancias(self, id_empresa: int, limite: int = 10) -> List[dict]:
        """Substâncias alergênicas mais reportadas entre os pacientes da
        empresa, com contagem de casos.
 
        Retorna lista de dicts, ordenada do mais frequente pro menos:
        [{"substancia": "Dipirona", "total": 18}, ...]
        """
        from src.models import db
        from sqlalchemy import func
        from src.models.pacientes import Paciente
 
        linhas = (
            db.session.query(
                Alergia.substancia.label("substancia"),
                func.count(Alergia.id).label("total"),
            )
            .join(Paciente, Alergia.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .group_by(Alergia.substancia)
            .order_by(func.count(Alergia.id).desc())
            .limit(limite)
            .all()
        )
        return [{"substancia": linha.substancia, "total": linha.total} for linha in linhas]
 
    # --- D2 (detalhe): gravidade das reações por substância ---
    def gravidade_por_substancia(self, id_empresa: int, substancia: str) -> dict:
        """Distribuição de gravidade (leve/moderada/grave) das reações
        registradas para uma substância específica -- usado como
        drill-down quando o usuário clica numa barra do ranking D2.
 
        Retorna dict, ex: {"leve": 5, "moderada": 10, "grave": 3}
        """
        from src.models import db
        from sqlalchemy import func
        from src.models.pacientes import Paciente
        from src.models.pacientes.reacao_alergia import ReacaoAlergia
 
        linhas = (
            db.session.query(
                ReacaoAlergia.gravidade.label("gravidade"),
                func.count(ReacaoAlergia.id).label("total"),
            )
            .join(Alergia, ReacaoAlergia.id_alergia == Alergia.id)
            .join(Paciente, Alergia.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(Alergia.substancia == substancia)
            .group_by(ReacaoAlergia.gravidade)
            .all()
        )
        return {linha.gravidade: linha.total for linha in linhas}