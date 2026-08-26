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