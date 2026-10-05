from datetime import datetime, timezone, timedelta
from typing import Optional

from src.core.interfaces import IRepository
from src.models import db
from src.models.pacientes import ConsentimentoSessaoAssinatura as Sessao


class ConsentimentoSessaoAssinaturaRepository(IRepository[Sessao]):

    def find_by_token(self, token: str, for_update: bool = False) -> Optional[Sessao]:
        """for_update=True trava a linha até o fim da transação (evita duas
        assinaturas simultâneas com o mesmo token)."""
        q = Sessao.query.filter_by(token=token)
        if for_update:
            q = q.with_for_update()
        return q.first()

    def save(self, sessao: Sessao, commit: bool = True) -> Sessao:
        db.session.add(sessao)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return sessao

    def expirar_pendentes_do_paciente(self, id_paciente: int) -> int:
        """Invalida links ainda pendentes do paciente (ao gerar um novo).
        Não commita: quem chama decide."""
        return (
            Sessao.query
            .filter_by(id_paciente=id_paciente, status="pendente")
            .update({"status": "expirado"}, synchronize_session=False)
        )

    def deletar_antigas(self, dias: int = 7) -> int:
        """Para o cron de limpeza: apaga sessões NÃO usadas e vencidas há X dias.
        Sessões 'usado' são mantidas (são prova da assinatura)."""
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        n = (
            Sessao.query
            .filter(Sessao.status != "usado", Sessao.expira_em < limite)
            .delete(synchronize_session=False)
        )
        db.session.commit()
        return n
    
    def delete():
        pass    
    
    def find_by_id():
        pass
    
    def find_by_uuid():
        pass