"""consentimento_sessao_assinatura_repository.py

Acesso a dados da sessão de assinatura digital do consentimento (o link por QR
code): busca pelo token (com trava de linha opcional), expiração dos links
pendentes de um paciente, limpeza de sessões antigas e gravação.

A sessão 'usado' é prova da assinatura e nunca é apagada pela limpeza.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.core.interfaces import IRepository
from src.models import db
from src.models.pacientes import ConsentimentoSessaoAssinatura as Sessao


class ConsentimentoSessaoAssinaturaRepository(IRepository[Sessao]):

    def find_by_token(self, token: str, for_update: bool = False) -> Optional[Sessao]:
        """for_update=True trava a linha até o fim da transação (evita duas assinaturas simultâneas
        com o mesmo token)."""
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
        """Invalida os links ainda pendentes do paciente (ao gerar um novo). Não commita: quem chama decide."""
        return (
            Sessao.query
            .filter_by(id_paciente=id_paciente, status="pendente")
            .update({"status": "expirado"}, synchronize_session=False)
        )

    def deletar_antigas(self, dias: int = 7) -> int:
        """Para o cron de limpeza: apaga sessões NÃO usadas e vencidas há X dias. As sessões 'usado'
        são mantidas (são prova da assinatura)."""
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        n = (
            Sessao.query
            .filter(Sessao.status != "usado", Sessao.expira_em < limite)
            .delete(synchronize_session=False)
        )
        db.session.commit()
        return n

    def delete(self, id: int):
        raise NotImplementedError("Sessão de assinatura não é apagada por id; use deletar_antigas.")

    def find_by_id(self, id: int):
        raise NotImplementedError("Sessão de assinatura é consultada pelo token (find_by_token).")

    def find_by_uuid(self, uuid: str):
        raise NotImplementedError("Sessão de assinatura é consultada pelo token (find_by_token).")
