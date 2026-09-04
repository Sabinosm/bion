from typing import Optional, List
from datetime import datetime, time, timezone, timedelta

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (
    Paciente, PacienteDadosPessoais, Alergia, ReacaoAlergia,
    DoencaCronica, MedicamentoEmUso, Consentimento, ObservacaoTipoSanguineo,
)
from sqlalchemy import func

class MedicamentoEmUsoRepository(IRepository[MedicamentoEmUso]):
    """Toda leitura "normal" (find_by_id, find_by_uuid, find_por_paciente,
    percentual_pacientes_em_uso_continuo) filtra `deletado == False`
    por padrão -- mesmo padrão de AlergiaRepository/
    DoencaCronicaRepository. find_apagados é o único ponto de acesso
    a registros soft-deletados."""

    def find_by_id(self, id: int) -> Optional[MedicamentoEmUso]:
        return (
            MedicamentoEmUso.query
            .filter(MedicamentoEmUso.id == id, MedicamentoEmUso.deletado == False)
            .first()
        )

    def find_by_uuid(self, uuid: str) -> Optional[MedicamentoEmUso]:
        # ALTERADO: agora existe uuid de verdade (era None antes, por
        # falta da coluna -- ver 08_medicamentos_em_uso_migration.sql).
        # Filtra deletado == False, mesmo padrão dos demais domínios.
        return (
            MedicamentoEmUso.query
            .filter(MedicamentoEmUso.uuid == uuid, MedicamentoEmUso.deletado == False)
            .first()
        )

    def find_by_uuid_incluindo_deletados(self, uuid: str) -> Optional[MedicamentoEmUso]:
        """NOVO: busca sem filtrar deletado -- usado quando o service
        precisa distinguir 'não existe' de 'existe mas está
        soft-deletado' (bloquear update, ou achar o registro pra
        restaurar). Mesmo padrão de Alergia/DoencaCronica."""
        return MedicamentoEmUso.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[MedicamentoEmUso]:
        return (
            MedicamentoEmUso.query
            .filter(MedicamentoEmUso.id_paciente == id_paciente, MedicamentoEmUso.deletado == False)
            .all()
        )

    def find_apagados(self, id_paciente: Optional[int] = None) -> List[MedicamentoEmUso]:
        """NOVO: único ponto de acesso a medicamentos soft-deletados.
        id_paciente opcional -- sem ele, lista todos os deletados da
        base; com ele, filtra por paciente."""
        query = MedicamentoEmUso.query.filter(MedicamentoEmUso.deletado == True)
        if id_paciente is not None:
            query = query.filter(MedicamentoEmUso.id_paciente == id_paciente)
        return query.all()

    def save(self, entity: MedicamentoEmUso) -> MedicamentoEmUso:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Mantido só por contrato com IRepository -- delete físico.
        NÃO deve ser chamado pela camada de service/controller de
        medicamento em uso; use soft_delete."""
        e = db.session.get(MedicamentoEmUso, id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def soft_delete(self, entity: MedicamentoEmUso, motivo: str, observacoes_delete: Optional[str] = None) -> MedicamentoEmUso:
        """Marca como removido sem apagar a linha. Não mexe em
        flag_em_uso/status_uso -- o estado clínico do tratamento fica
        preservado intacto (ver comentário no model). Idempotente:
        chamar de novo num registro já deletado só atualiza os campos
        de novo."""
        entity.deletado = True
        entity.deletado_em = datetime.now(timezone.utc)
        entity.motivo_delete = motivo
        entity.observacoes_delete = observacoes_delete
        db.session.add(entity)
        db.session.commit()
        return entity

    def restaurar(self, entity: MedicamentoEmUso) -> MedicamentoEmUso:
        """NOVO: reverte um soft delete. flag_em_uso/status_uso nunca
        foram alterados pelo soft delete, então voltam junto sem
        precisar de parâmetro adicional."""
        entity.deletado = False
        entity.deletado_em = None
        entity.motivo_delete = None
        entity.observacoes_delete = None
        db.session.add(entity)
        db.session.commit()
        return entity
    
     # --- F2: Pacientes em uso contínuo de medicação (%) ---
    def percentual_pacientes_em_uso_continuo(self, id_empresa: int) -> dict:
        """% de pacientes (distintos) da empresa com status_uso='ativo'
        em pelo menos 1 medicamento, sobre o total de pacientes cadastrados.
        Filtra MedicamentoEmUso.deletado == False -- medicamento
        removido não deve contar como "em uso contínuo".
 
        Retorna: {"total_pacientes": int, "em_uso_continuo": int, "percentual": float}
        """
        from src.models import db
        from sqlalchemy import func
        from src.models.pacientes import Paciente
 
        total_pacientes = (
            db.session.query(func.count(Paciente.id))
            .filter(Paciente.id_empresa == id_empresa)
            .scalar() or 0
        )
 
        em_uso = (
            db.session.query(func.count(func.distinct(MedicamentoEmUso.id_paciente)))
            .join(Paciente, MedicamentoEmUso.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(MedicamentoEmUso.status_uso == "ativo")
            .filter(MedicamentoEmUso.deletado == False)
            .scalar() or 0
        )
 
        percentual = round((em_uso / total_pacientes) * 100, 1) if total_pacientes else 0.0
 
        return {"total_pacientes": total_pacientes, "em_uso_continuo": em_uso, "percentual": percentual}