from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (
    Paciente, PacienteDadosPessoais, Alergia, ReacaoAlergia,
    DoencaCronica, MedicamentoEmUso, Consentimento, ObservacaoTipoSanguineo,
)
from datetime import datetime, time, timezone, timedelta
from sqlalchemy import func



class PacienteRepository(IRepository[Paciente]):

    def find_by_id(self, id: int) -> Optional[Paciente]:
        return db.session.get(Paciente, id)

    def find_by_uuid(self, uuid: str) -> Optional[Paciente]:
        return Paciente.query.filter_by(uuid=uuid).first()

    def find_por_cpf_hash(self, cpf_hash: str) -> Optional[Paciente]:
        """Busca por CPF via hash HMAC-SHA256 (determinístico), não pelo
        valor cifrado com AES-256-GCM (ver nota original mantida)."""
        pessoal = PacienteDadosPessoais.query.filter_by(cpf_hash=cpf_hash).first()
        return pessoal.paciente if pessoal else None

    def save(self, entity: Paciente) -> Paciente:
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

    def find_all(self) -> List[Paciente]:
        return Paciente.query.all()
    
    def count_pacientes_hoje(self, id_empresa: int) -> int:
            from src.models.usuarios import Usuario
            hoje = datetime.now(timezone.utc).date()
            inicio_dia = datetime.combine(hoje, time.min, tzinfo=timezone.utc)
            fim_dia = datetime.combine(hoje, time.max, tzinfo=timezone.utc)
    
            return (
                db.session.query(func.count(Paciente.id))
                .join(Usuario, Paciente.cadastrado_por == Usuario.id)
                .filter(Usuario.id_empresa == id_empresa)
                .filter(Paciente.criado_em >= inicio_dia)
                .filter(Paciente.criado_em < fim_dia)
                .scalar()
            )
            
    
    def count_pacientes(self, id_empresa: int) -> int:
        from src.models.usuarios import Usuario
            
        return (
                db.session.query(func.count(Paciente.id))
                .join(Usuario, Paciente.cadastrado_por == Usuario.id)
                .filter(Usuario.id_empresa == id_empresa)
                .scalar()
            )
     # --- F1: Doenças crônicas mais comuns na base ---
    def top_cid_ativas(self, id_empresa: int, limite: int = 10) -> list:
        """Ranking de codigo_cid10 com status='ativa', entre os pacientes
        da empresa. Não filtra por período -- é o estado atual da base,
        não um evento pontual.
 
        Retorna: [{"codigo_cid10": "I10", "descricao_cid10": "Hipertensão", "total": 214}, ...]
        """
        from src.models import db
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.pacientes import Paciente
 
        linhas = (
            db.session.query(
                DoencaCronica.codigo_cid10.label("codigo"),
                DoencaCronica.descricao_cid10.label("descricao"),
                func.count(DoencaCronica.id).label("total"),
            )
            .join(Paciente, DoencaCronica.id_paciente == Paciente.id)
            .join(Usuario, Paciente.cadastrado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(DoencaCronica.status == "ativa")
            .group_by(DoencaCronica.codigo_cid10, DoencaCronica.descricao_cid10)
            .order_by(func.count(DoencaCronica.id).desc())
            .limit(limite)
            .all()
        )
        return [
            {"codigo_cid10": linha.codigo, "descricao_cid10": linha.descricao, "total": linha.total}
            for linha in linhas
        ]