"""
empresa_protocolo_repository.py

Acesso a dados da liberação institucional de protocolos: consultas e
persistência dos vínculos entre empresa e protocolo do catálogo, sem regra de
negócio. Só existem vínculos para protocolos que a empresa já tocou; o
cruzamento com o catálogo inteiro é feito no service. A gravação traduz
violações de unicidade (vínculo duplicado ou segundo padrão no mesmo escopo)
em conflito, para que operações simultâneas não resultem em erro 500.
"""

from typing import Optional, List

from sqlalchemy.exc import IntegrityError

from src.models import db
from src.core.exceptions import ConflictoError
from src.core.interfaces import IRepository
from src.models.corp import EmpresaProtocolo


class EmpresaProtocoloRepository(IRepository[EmpresaProtocolo]):

    def find_by_id(self, id: int) -> Optional[EmpresaProtocolo]:
        return db.session.get(EmpresaProtocolo, id)

    def find_by_uuid(self, uuid: str):
        return super().find_by_uuid(uuid)

    def find_por_empresa_e_protocolo(self, id_empresa: int, id_protocolo_catalogo: int) -> Optional[EmpresaProtocolo]:
        return EmpresaProtocolo.query.filter_by(
            id_empresa=id_empresa, id_protocolo_catalogo=id_protocolo_catalogo
        ).first()

    def find_all_por_empresa(self, id_empresa: int) -> List[EmpresaProtocolo]:
        """Vínculos já criados para a empresa (não inclui protocolos do catálogo nunca tocados)."""
        return EmpresaProtocolo.query.filter_by(id_empresa=id_empresa).all()

    def find_ativos_por_empresa(self, id_empresa: int) -> List[EmpresaProtocolo]:
        return EmpresaProtocolo.query.filter_by(id_empresa=id_empresa, ativo=True).all()

    def find_default_do_escopo(self, id_empresa: int, escopo: str) -> Optional[EmpresaProtocolo]:
        """Default institucional atual de um escopo, para liberar o slot antes de
        definir outro (UNIQUE uq_emp_default_por_escopo)."""
        return EmpresaProtocolo.query.filter_by(
            id_empresa=id_empresa, escopo_default_institucional=escopo
        ).first()

    def find_empresa_com_catatlogo(
        self,
        id_empresa: int,
        id_protocolo_catalogo: int,
        apenas_ativo: bool = None,
        apenas_inativo: bool = None,
    ) -> Optional[EmpresaProtocolo]:
        """Vínculo da empresa com um protocolo, opcionalmente só se ativo ou só se inativo."""
        filtros = {"id_empresa": id_empresa, "id_protocolo_catalogo": id_protocolo_catalogo}
        if apenas_ativo:
            filtros["ativo"] = True
        elif apenas_inativo:
            filtros["ativo"] = False
        return EmpresaProtocolo.query.filter_by(**filtros).first()

    def contar_ativos(self, id_empresa: int) -> int:
        return EmpresaProtocolo.query.filter_by(id_empresa=id_empresa, ativo=True).count()

    def save(self, entity: EmpresaProtocolo, commit: bool = True) -> EmpresaProtocolo:
        """Persiste o vínculo. Com commit=False só faz flush (mantém a transação aberta).

        Raises:
            ConflictoError: violação de unicidade (PK composta ou default por
                escopo), tipicamente dois admins agindo ao mesmo tempo.
        """
        db.session.add(entity)
        try:
            if commit:
                db.session.commit()
            else:
                db.session.flush()
        except IntegrityError:
            db.session.rollback()
            raise ConflictoError("Operação simultânea detectada. Tente novamente.")
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[EmpresaProtocolo]:
        return EmpresaProtocolo.query.all()