"""Repositório de acesso a dados da entidade Prescricao."""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import Prescricao


class PrescricaoRepository(IRepository[Prescricao]):

    def find_by_uuid(self, uuid: str) -> Optional[Prescricao]:
        return db.session.get(Prescricao, uuid)
    
    def find_by_id(self, id: int) -> Optional[Prescricao]:
        return db.session.get(Prescricao, id)

    def save(self, entity: Prescricao) -> Prescricao:
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

    def find_all(self) -> List[Prescricao]:
        return Prescricao.query.all()

    # --- D4: Medicamentos mais prescritos por classe farmacêutica ---
    def top_por_classe(self, id_empresa: int, dias: int = 30, limite: int = 10) -> List[dict]:
        """Ranking de classes farmacêuticas mais prescritas.

        Caminho: Prescricao -> ResultadoPrescricao -> Atendimento ->
        realizado_por -> Usuario; e Prescricao -> CatalogoMedicamentos
        para a classe.

        Retorna: [{"classe_farmaceutica": "Analgésico", "total": 58}, ...]
        """
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.clinico import ResultadoPrescricao, Atendimento
        from src.models.catalogos import CatalogoMedicamentos

        limite_data = datetime.now(timezone.utc) - timedelta(days=dias)

        linhas = (
            db.session.query(
                CatalogoMedicamentos.classe_farmaceutica.label("classe"),
                func.count(Prescricao.id).label("total"),
            )
            .join(CatalogoMedicamentos, Prescricao.id_catalogo == CatalogoMedicamentos.id)
            .join(ResultadoPrescricao, Prescricao.id_resultado_prescricao == ResultadoPrescricao.id)
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(ResultadoPrescricao.data_hora_formulacao >= limite_data)
            .filter(CatalogoMedicamentos.classe_farmaceutica.isnot(None))
            .group_by(CatalogoMedicamentos.classe_farmaceutica)
            .order_by(func.count(Prescricao.id).desc())
            .limit(limite)
            .all()
        )
        return [{"classe_farmaceutica": linha.classe, "total": linha.total} for linha in linhas]

    # --- D4 (detalhe): top princípios ativos dentro de 1 classe ---
    def top_principios_ativos_por_classe(self, id_empresa: int, classe: str, dias: int = 30, limite: int = 10) -> List[dict]:
        """Drill-down de D4: quando o usuário clica numa classe no
        gráfico, mostra quais princípios ativos específicos compõem
        aquele total.
        """
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.clinico import ResultadoPrescricao, Atendimento
        from src.models.catalogos import CatalogoMedicamentos

        limite_data = datetime.now(timezone.utc) - timedelta(days=dias)

        linhas = (
            db.session.query(
                CatalogoMedicamentos.principio_ativo.label("principio_ativo"),
                func.count(Prescricao.id).label("total"),
            )
            .join(CatalogoMedicamentos, Prescricao.id_catalogo == CatalogoMedicamentos.id)
            .join(ResultadoPrescricao, Prescricao.id_resultado_prescricao == ResultadoPrescricao.id)
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(ResultadoPrescricao.data_hora_formulacao >= limite_data)
            .filter(CatalogoMedicamentos.classe_farmaceutica == classe)
            .group_by(CatalogoMedicamentos.principio_ativo)
            .order_by(func.count(Prescricao.id).desc())
            .limit(limite)
            .all()
        )
        return [{"principio_ativo": linha.principio_ativo, "total": linha.total} for linha in linhas]