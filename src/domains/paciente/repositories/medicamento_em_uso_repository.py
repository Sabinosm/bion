"""medicamento_em_uso_repository.py

Acesso a dados de MedicamentoEmUso: listagem do paciente (com o catálogo já
carregado, sem N+1), checagem de duplicata ativa, fechamento clínico do
tratamento, soft delete e o percentual de pacientes em uso contínuo.

Toda leitura "normal" filtra deletado == False; find_apagados é o único ponto de
acesso a registros soft-deletados (fora a busca que os inclui, usada pelo service
para distinguir 404 de 409). Os métodos de escrita aceitam commit=False para só
dar flush, de modo que o service componha operações atômicas (substituir =
inserir o novo + fechar o antigo) e a última chamada, com commit=True, confirme
tudo. Se qualquer flush ou commit falhar, a sessão inteira sofre rollback. Delete
físico não existe: levanta NotImplementedError.
"""
from datetime import datetime, date, timezone
from typing import Optional, List

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import Paciente, MedicamentoEmUso


class MedicamentoEmUsoRepository(IRepository[MedicamentoEmUso]):

    # ---------- leitura ----------
    def find_by_id(self, id: int) -> Optional[MedicamentoEmUso]:
        return (
            MedicamentoEmUso.query
            .filter(MedicamentoEmUso.id == id, MedicamentoEmUso.deletado.is_(False))
            .first()
        )

    def find_by_uuid(self, uuid: str) -> Optional[MedicamentoEmUso]:
        return (
            MedicamentoEmUso.query
            .filter(MedicamentoEmUso.uuid == uuid, MedicamentoEmUso.deletado.is_(False))
            .first()
        )

    def find_by_uuid_incluindo_deletados(self, uuid: str) -> Optional[MedicamentoEmUso]:
        return MedicamentoEmUso.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int, apenas_ativos: bool = False) -> List[MedicamentoEmUso]:
        """Não deletados do paciente (ativos primeiro, mais recentes antes). Carrega o catálogo e o
        atendimento de origem junto, para evitar N+1 no to_dict."""
        q = (
            MedicamentoEmUso.query
            .options(joinedload(MedicamentoEmUso.catalogo_medicamentos),
                     joinedload(MedicamentoEmUso.atendimento_origem))
            .filter(MedicamentoEmUso.id_paciente == id_paciente,
                    MedicamentoEmUso.deletado.is_(False))
        )
        if apenas_ativos:
            q = q.filter(MedicamentoEmUso.status_uso == "ativo")
        return q.order_by(
            (MedicamentoEmUso.status_uso == "ativo").desc(),
            MedicamentoEmUso.desde.desc(),
            MedicamentoEmUso.id.desc(),
        ).all()

    def existe_ativo_do_catalogo(self, id_paciente: int, id_catalogo: int,
                                 excluir_id: Optional[int] = None) -> bool:
        """Já há um registro ATIVO deste medicamento do catálogo para o paciente? (barra duplicata
        ao registrar e ao restaurar)."""
        q = MedicamentoEmUso.query.filter(
            MedicamentoEmUso.id_paciente == id_paciente,
            MedicamentoEmUso.id_catalogo == id_catalogo,
            MedicamentoEmUso.status_uso == "ativo",
            MedicamentoEmUso.deletado.is_(False),
        )
        if excluir_id is not None:
            q = q.filter(MedicamentoEmUso.id != excluir_id)
        return db.session.query(q.exists()).scalar()

    def find_apagados(self, id_paciente: Optional[int] = None) -> List[MedicamentoEmUso]:
        query = MedicamentoEmUso.query.filter(MedicamentoEmUso.deletado.is_(True))
        if id_paciente is not None:
            query = query.filter(MedicamentoEmUso.id_paciente == id_paciente)
        return query.all()

    # ---------- escrita ----------
    def confirmar(self, commit: bool = True) -> None:
        """commit=True: commita; commit=False: só flush. Se falhar, desfaz a sessão inteira."""
        try:
            if commit:
                db.session.commit()
            else:
                db.session.flush()
        except Exception:
            db.session.rollback()
            raise

    def rollback(self) -> None:
        db.session.rollback()

    def save(self, entity: MedicamentoEmUso, commit: bool = True) -> MedicamentoEmUso:
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def add(self, entity: MedicamentoEmUso, commit: bool = True) -> MedicamentoEmUso:
        """Insere um registro novo (com commit=False já tem entity.id)."""
        return self.save(entity, commit=commit)

    def fechar(self, entity: MedicamentoEmUso, status_uso: str, ate: date,
               id_usuario: int, id_atendimento: int,
               id_substituida_por: Optional[int] = None,
               commit: bool = True) -> MedicamentoEmUso:
        """Encerra clinicamente o tratamento (não apaga nada)."""
        entity.status_uso = status_uso
        entity.ate = ate
        entity.encerrado_por = id_usuario
        entity.id_atendimento_encerramento = id_atendimento
        entity.id_substituida_por = id_substituida_por
        return self.save(entity, commit=commit)

    def soft_delete(self, entity: MedicamentoEmUso, motivo: str,
                    observacoes_delete: Optional[str],
                    id_usuario: int, id_atendimento: int,
                    commit: bool = True) -> MedicamentoEmUso:
        """Marca como removido sem apagar a linha e sem mexer no estado clínico (status_uso e ate)."""
        entity.deletado = True
        entity.deletado_em = datetime.now(timezone.utc)
        entity.motivo_delete = motivo
        entity.observacoes_delete = observacoes_delete
        entity.deletado_por = id_usuario
        entity.id_atendimento_delecao = id_atendimento
        return self.save(entity, commit=commit)

    def restaurar(self, entity: MedicamentoEmUso, commit: bool = True) -> MedicamentoEmUso:
        """Reverte um soft delete (limpa todos os campos de remoção)."""
        entity.deletado = False
        entity.deletado_em = None
        entity.motivo_delete = None
        entity.observacoes_delete = None
        entity.deletado_por = None
        entity.id_atendimento_delecao = None
        return self.save(entity, commit=commit)

    def delete(self, id: int) -> bool:
        """Nada é apagado fisicamente. O contrato do IRepository fica só para a classe ser
        instanciável; use soft_delete."""
        raise NotImplementedError(
            "Medicamento em uso não pode ser apagado fisicamente; use soft_delete."
        )

    # ---------- estatísticas ----------
    def percentual_pacientes_em_uso_continuo(self, id_empresa: int) -> dict:
        """% de pacientes (distintos) da empresa com ao menos 1 medicamento ATIVO (status_uso='ativo'
        e não deletado), sobre o total de pacientes cadastrados.

        Retorna: {"total_pacientes": int, "em_uso_continuo": int, "percentual": float}
        """
        total_pacientes = (
            db.session.query(func.count(Paciente.id))
            .filter(Paciente.id_empresa == id_empresa)
            .scalar() or 0
        )

        em_uso = (
            db.session.query(func.count(func.distinct(MedicamentoEmUso.id_paciente)))
            .join(Paciente, MedicamentoEmUso.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(MedicamentoEmUso.ativo)
            .scalar() or 0
        )

        percentual = round((em_uso / total_pacientes) * 100, 1) if total_pacientes else 0.0

        return {"total_pacientes": total_pacientes, "em_uso_continuo": em_uso, "percentual": percentual}
