"""Repositório de acesso a dados de EmpresaProtocolo (liberação institucional de protocolos)."""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.corp import EmpresaProtocolo


class EmpresaProtocoloRepository(IRepository[EmpresaProtocolo]):

    def find_by_id(self, id: int) -> Optional[EmpresaProtocolo]:
        return db.session.get(EmpresaProtocolo, id)

    def find_por_empresa_e_protocolo(self, id_empresa: int, id_protocolo_catalogo: int) -> Optional[EmpresaProtocolo]:
        return EmpresaProtocolo.query.filter_by(
            id_empresa=id_empresa, id_protocolo_catalogo=id_protocolo_catalogo
        ).first()

    def find_all_por_empresa(self, id_empresa: int) -> List[EmpresaProtocolo]:
        """Lista todos os vínculos já criados para a empresa (não inclui protocolos
        do catálogo nunca tocados — isso é resolvido no Service, que cruza com o catálogo)."""
        return EmpresaProtocolo.query.filter_by(id_empresa=id_empresa).all()

    def find_ativos_por_empresa(self, id_empresa: int) -> List[EmpresaProtocolo]:
        return EmpresaProtocolo.query.filter_by(id_empresa=id_empresa, ativo=True).all()

    def find_default_do_escopo(self, id_empresa: int, escopo: str) -> Optional[EmpresaProtocolo]:
        """Localiza o default institucional atual de um escopo, para liberar o
        slot antes de definir outro (UNIQUE uq_emp_default_por_escopo)."""
        return EmpresaProtocolo.query.filter_by(
            id_empresa=id_empresa, escopo_default_institucional=escopo
        ).first()

    def contar_ativos(self, id_empresa: int) -> int:
        return EmpresaProtocolo.query.filter_by(id_empresa=id_empresa, ativo=True).count()

    def save(self, entity: EmpresaProtocolo, commit: bool = True) -> EmpresaProtocolo:
        db.session.add(entity)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
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