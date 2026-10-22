"""
repository.py

Acesso a dados do domínio Empresa: consultas e persistência da entidade, sem
regra de negócio. CNPJ e CNES não são colunas da empresa, e sim registros na
tabela de identificadores; por isso a busca por eles é feita com junção
explícita, filtrando pelo tipo do identificador.
"""

from typing import Optional

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
        return self._find_por_identificador("cnpj", cnpj)

    def find_by_cnes(self, cnes: str) -> Optional[Empresa]:
        return self._find_por_identificador("cnes", cnes)

    def _find_por_identificador(self, tipo: str, valor: str) -> Optional[Empresa]:
        """Busca a empresa dona do identificador (`tipo`, `valor`) via junção."""
        return (
            Empresa.query
            .join(EmpresaIdentificador, EmpresaIdentificador.id_empresa == Empresa.id)
            .filter(
                EmpresaIdentificador.tipo_identificador == tipo,
                EmpresaIdentificador.valor == valor,
            )
            .first()
        )

    def save(self, entity: Empresa, commit: bool = True) -> Empresa:
        """Persiste a empresa. Com commit=False só faz flush (gera o id, mantém a transação aberta)."""
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

    def find_regiao_geografica(self, id: int):
        """Retorna a região geográfica da empresa, ou None se a empresa não existir."""
        # Import local para evitar dependência circular entre os domínios.
        from src.domains.regiao.service import RegiaoService

        empresa = self.find_by_id(id)
        if not empresa:
            return None
        return RegiaoService.buscar_por_id(empresa.id_regiao_geografica)