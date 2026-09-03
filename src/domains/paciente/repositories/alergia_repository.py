from typing import Optional, List
from datetime import datetime, timezone

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (Alergia, Paciente)



class AlergiaRepository(IRepository[Alergia]):
    """Toda leitura "normal" (find_by_id, find_by_uuid, find_por_paciente
    e as estatísticas abaixo) filtra `deletado == False` por padrão --
    mesmo padrão de DoencaCronicaRepository. find_apagados é o único
    ponto de acesso a registros soft-deletados."""

    def find_by_id(self, id: int) -> Optional[Alergia]:
        return (
            Alergia.query
            .filter(Alergia.id == id, Alergia.deletado == False)
            .first()
        )

    def find_by_uuid(self, uuid: str) -> Optional[Alergia]:
        return (
            Alergia.query
            .filter(Alergia.uuid == uuid, Alergia.deletado == False)
            .first()
        )

    def find_by_uuid_incluindo_deletados(self, uuid: str) -> Optional[Alergia]:
        """NOVO: busca sem filtrar deletado -- usado quando o service
        precisa distinguir 'não existe' de 'existe mas está
        soft-deletado' (bloquear update, ou achar o registro pra
        restaurar). Ver mesmo padrão em DoencaCronicaRepository."""
        return Alergia.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Alergia]:
        return (
            Alergia.query
            .filter(Alergia.id_paciente == id_paciente, Alergia.deletado == False)
            .all()
        )

    def find_apagados(self, id_paciente: Optional[int] = None) -> List[Alergia]:
        """NOVO: único ponto de acesso a alergias soft-deletadas.
        id_paciente opcional -- sem ele, lista todas as deletadas da
        base (uso de auditoria/admin); com ele, filtra por paciente."""
        query = Alergia.query.filter(Alergia.deletado == True)
        if id_paciente is not None:
            query = query.filter(Alergia.id_paciente == id_paciente)
        return query.all()

    def save(self, entity: Alergia) -> Alergia:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Mantido só por contrato com IRepository -- delete físico.
        NÃO deve ser chamado pela camada de service/controller de
        alergia; use soft_delete."""
        e = db.session.get(Alergia, id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def delete_by_uuid(self, uuid: str) -> bool:
        """Mantido só por contrato/compatibilidade -- delete físico
        (remove a alergia E suas reações via cascade). NÃO deve ser
        chamado pela camada de service/controller de alergia; use
        soft_delete, que preserva o histórico de reações intacto."""
        e = Alergia.query.filter_by(uuid=uuid).first()
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def soft_delete(self, entity: Alergia, motivo: str, observacoes_delete: Optional[str] = None) -> Alergia:
        """Marca a alergia como removida sem apagar a linha nem as
        reações associadas (cascade de delete físico não é acionado
        aqui -- reacoes continuam existindo, vinculadas normalmente,
        só ficam invisíveis por tabela já que não há listagem direta
        de reação fora do objeto alergia). Idempotente: chamar de novo
        num registro já deletado só atualiza os campos de novo."""
        entity.deletado = True
        entity.deletado_em = datetime.now(timezone.utc)
        entity.motivo_delete = motivo
        entity.observacoes_delete = observacoes_delete
        db.session.add(entity)
        db.session.commit()
        return entity

    def restaurar(self, entity: Alergia) -> Alergia:
        """NOVO: reverte um soft delete."""
        entity.deletado = False
        entity.deletado_em = None
        entity.motivo_delete = None
        entity.observacoes_delete = None
        db.session.add(entity)
        db.session.commit()
        return entity

    # --- A2/E2/F4/D2: estatísticas ---
    # REMOVIDO: tempo_medio_por_tipo, atendimentos_por_status e
    # tempo_medio_por_tipo_periodo chamavam self.repo.xxx() -- código
    # de outra camada (service) colado aqui por engano; repository não
    # tem self.repo. Se essas estatísticas ainda são necessárias,
    # pertencem a AtendimentoRepository/Service (domínio diferente de
    # Alergia), não aqui -- me avisa que endereçamos separado.

    # --- F4: Gravidade geral das reações alérgicas (sem filtro por substância) ---
    def gravidade_geral(self, id_empresa: int) -> dict:
        """Mesma lógica de gravidade_por_substancia, mas sem o filtro
        WHERE substancia=... -- visão agregada de todas as reações da
        empresa, não drill-down de 1 substância específica. Filtra
        Alergia.deletado == False -- reação de alergia soft-deletada
        não deve entrar na estatística.

        Retorna: {"leve": 30, "moderada": 45, "grave": 9}
        """
        from sqlalchemy import func
        from src.models.pacientes.reacao_alergia import ReacaoAlergia

        linhas = (
            db.session.query(
                    ReacaoAlergia.gravidade.label("gravidade"),
                    func.count(ReacaoAlergia.id).label("total"),
                )
                .join(Alergia, ReacaoAlergia.id_alergia == Alergia.id)
                .join(Paciente, Alergia.id_paciente == Paciente.id)
                .filter(Paciente.id_empresa == id_empresa)
                .filter(Alergia.deletado == False)
                .group_by(ReacaoAlergia.gravidade)
                .all()
        )
        return {linha.gravidade: linha.total for linha in linhas}
    
    
    # --- D2: Alergias mais reportadas (por substância) ---
    def top_substancias(self, id_empresa: int, limite: int = 10) -> List[dict]:
        """Substâncias alergênicas mais reportadas entre os pacientes da
        empresa, com contagem de casos. Filtra deletado == False --
        alergia removida não deve inflar o ranking.
 
        Retorna lista de dicts, ordenada do mais frequente pro menos:
        [{"substancia": "Dipirona", "total": 18}, ...]
        """
        from sqlalchemy import func
 
        linhas = (
            db.session.query(
                Alergia.substancia.label("substancia"),
                func.count(Alergia.id).label("total"),
            )
            .join(Paciente, Alergia.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(Alergia.deletado == False)
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
        Filtra deletado == False pelo mesmo motivo das estatísticas
        acima.
 
        Retorna dict, ex: {"leve": 5, "moderada": 10, "grave": 3}
        """
        from sqlalchemy import func
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
            .filter(Alergia.deletado == False)
            .group_by(ReacaoAlergia.gravidade)
            .all()
        )
        return {linha.gravidade: linha.total for linha in linhas}