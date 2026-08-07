"""
ALTERADO: find_by_cnpj não pode mais usar filter_by(cnpj=...) direto,
já que cnpj virou @property (não coluna). Precisa de JOIN explícito
com EmpresaIdentificador.
"""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.corp.empresa import Empresa
from src.models.corp.empresa_identificador import EmpresaIdentificador


class EmpresaRepository(IRepository[Empresa]):

    def find_by_id(self, id: int) -> Optional[Empresa]:
        return db.session.get(Empresa, id)

    def find_by_uuid(self, uuid: str) -> Optional[Empresa]:
        return Empresa.query.filter_by(uuid=uuid).first()

    def find_by_cnpj(self, cnpj: str) -> Optional[Empresa]:
        """Busca empresa pelo CNPJ, agora via join com EmpresaIdentificador."""
        return (
            Empresa.query
            .join(EmpresaIdentificador, EmpresaIdentificador.id_empresa == Empresa.id)
            .filter(
                EmpresaIdentificador.tipo_identificador == "cnpj",
                EmpresaIdentificador.valor == cnpj,
            )
            .first()
        )
    
    def find_by_cnes(self, cnes: str) -> Optional[Empresa]:
        """Busca empresa pelo CNES, agora via join com EmpresaIdentificador."""
        return (
            Empresa.query
            .join(EmpresaIdentificador, EmpresaIdentificador.id_empresa == Empresa.id)
            .filter(
                EmpresaIdentificador.tipo_identificador == "cnes",
                EmpresaIdentificador.valor == cnes,
            )
            .first()
        )

    def save(self, entity: Empresa, commit: bool = True) -> Empresa:
        if commit == True:
            db.session.add(entity)
            db.session.commit()
        else:
            db.session.add(entity)
            db.session.flush()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True