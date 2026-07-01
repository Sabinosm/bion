from typing import Optional, List

from src.database import db
from src.core.interfaces import IRepository
from src.database.auditoria import LogAcesso, LogAlteracao


class LogAcessoRepository(IRepository[LogAcesso]):

    def find_by_id(self, id: int) -> Optional[LogAcesso]:
        return db.session.get(LogAcesso, id)

    def find_by_uuid(self, uuid: str) -> Optional[LogAcesso]:
        return LogAcesso.query.filter_by(uuid=uuid).first()

    def find_por_usuario(self, id_usuario: int) -> List[LogAcesso]:
        return LogAcesso.query.filter_by(id_usuario=id_usuario).order_by(
            LogAcesso.data_hora.desc()).limit(200).all()

    def save(self, entity: LogAcesso) -> LogAcesso:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        # Logs de acesso são imutáveis por design (auditoria/LGPD) — exclusão não é permitida.
        return False

    def find_all(self) -> List[LogAcesso]:
        return LogAcesso.query.order_by(LogAcesso.data_hora.desc()).limit(500).all()


class LogAlteracaoRepository(IRepository[LogAlteracao]):

    def find_by_id(self, id: int) -> Optional[LogAlteracao]:
        return db.session.get(LogAlteracao, id)

    def find_by_uuid(self, uuid: str) -> Optional[LogAlteracao]:
        return LogAlteracao.query.filter_by(uuid=uuid).first()

    def find_por_registro(self, tabela_origem: str, uuid_registro: str) -> List[LogAlteracao]:
        return LogAlteracao.query.filter_by(
            tabela_origem=tabela_origem, uuid_registro=uuid_registro
        ).order_by(LogAlteracao.alterado_em.desc()).all()

    def save(self, entity: LogAlteracao) -> LogAlteracao:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        # Trilha de auditoria é imutável por design — exclusão não é permitida.
        return False

    def find_all(self) -> List[LogAlteracao]:
        return LogAlteracao.query.order_by(LogAlteracao.alterado_em.desc()).limit(500).all()
