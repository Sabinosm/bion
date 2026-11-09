"""consentimento_repository.py

Acesso a dados de Consentimento LGPD: busca por UUID, listagem e consentimento
ativo do paciente. O consentimento é prova LGPD (quem consentiu, quando, com qual
termo e hash), então não se apaga: para desfazer, revoga-se (status 'revogado').

commit/flush/rollback vivem AQUI, nunca nos services. save(commit=False) só faz
flush, para o service compor várias escritas (revogar o ativo anterior + criar o
novo + fechar a sessão de assinatura) num único commit.
"""
from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import Consentimento


class ConsentimentoRepository(IRepository[Consentimento]):

    # ------------------------------------------------------------ transação
    def confirmar(self, commit: bool = True) -> None:
        """Commit, ou só flush se o chamador vai comitar depois (mantém a atomicidade do log)."""
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    # ---------------------------------------------------------------- leitura
    def find_by_id(self, id: int) -> Optional[Consentimento]:
        return db.session.get(Consentimento, id)

    def find_by_uuid(self, uuid: str) -> Optional[Consentimento]:
        return Consentimento.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Consentimento]:
        return Consentimento.query.filter_by(id_paciente=id_paciente).all()

    def find_ativo_por_paciente(self, id_paciente: int) -> Optional[Consentimento]:
        """O consentimento ativo do paciente. Se por legado houver mais de um, o mais recente."""
        return (
            Consentimento.query
            .filter_by(id_paciente=id_paciente, status="ativo")
            .order_by(Consentimento.id.desc())
            .first()
        )

    def find_ativos_por_paciente(self, id_paciente: int, for_update: bool = False) -> List[Consentimento]:
        """Todos os ativos (normalmente 0 ou 1; mais de 1 = dado legado sujo). for_update trava as
        linhas até o fim da transação."""
        q = Consentimento.query.filter_by(id_paciente=id_paciente, status="ativo")
        if for_update:
            q = q.with_for_update()
        return q.all()

    # --------------------------------------------------------------- escrita
    def save(self, entity: Consentimento, commit: bool = True) -> Consentimento:
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int) -> bool:
        """Consentimento é prova LGPD e não se apaga; para desfazer use revogar (status 'revogado').
        O método existe só para cumprir o IRepository."""
        raise NotImplementedError(
            "Consentimento não pode ser removido; revogue-o (ConsentimentoService.revogar)."
        )
