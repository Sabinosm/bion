from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (
    Paciente, PacienteDadosPessoais, Alergia, ReacaoAlergia,
    DoencaCronica, MedicamentoEmUso, Consentimento, ObservacaoTipoSanguineo,
)
from datetime import datetime, time, timezone, timedelta
from sqlalchemy import func


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

    # --- D2: Alergias mais reportadas (por substância) ---
    def top_substancias(self, id_empresa: int, limite: int = 10) -> List[dict]:
        """Substâncias alergênicas mais reportadas entre os pacientes da
        empresa, com contagem de casos.
 
        Filtra por empresa via Paciente.cadastrado_por -> Usuario, mesmo
        padrão usado em PacienteRepository.count_pacientes.
 
        Retorna lista de dicts, ordenada do mais frequente pro menos:
        [{"substancia": "Dipirona", "total": 18}, ...]
        """
        from src.models import db
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.pacientes import Paciente
 
        linhas = (
            db.session.query(
                Alergia.substancia.label("substancia"),
                func.count(Alergia.id).label("total"),
            )
            .join(Paciente, Alergia.id_paciente == Paciente.id)
            .join(Usuario, Paciente.cadastrado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
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
        from src.models.usuarios import Usuario
        from src.models.pacientes import Paciente
        from src.models.pacientes.reacao_alergia import ReacaoAlergia
 
        linhas = (
            db.session.query(
                ReacaoAlergia.gravidade.label("gravidade"),
                func.count(ReacaoAlergia.id).label("total"),
            )
            .join(Alergia, ReacaoAlergia.id_alergia == Alergia.id)
            .join(Paciente, Alergia.id_paciente == Paciente.id)
            .join(Usuario, Paciente.cadastrado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(Alergia.substancia == substancia)
            .group_by(ReacaoAlergia.gravidade)
            .all()
        )
        return {linha.gravidade: linha.total for linha in linhas}
 