"""
EmpresaIdentificador — espelha Organization.identifier[] do FHIR.

Extrai o CNPJ (antes coluna solta em Empresa) para uma tabela própria,
já preparada para acomodar CNES (registro de estabelecimento de saúde
no DataSUS) no futuro, sem precisar de outra migração.
"""

from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class EmpresaIdentificador(db.Model):
    __tablename__ = "empresa_identificador"

    id = db.Column("id_empresa_identificador", BigIntPK, primary_key=True, autoincrement=True)
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresa.id_empresa"), nullable=False)
    tipo_identificador = db.Column(db.Enum("cnpj", "cnes"), nullable=False)
    valor = db.Column(db.String(50), nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    empresa = db.relationship("Empresa", back_populates="identificadores")

    def to_dict(self):
        return {"tipo": self.tipo_identificador, "valor": self.valor}

    def __repr__(self):
        return f"<EmpresaIdentificador {self.tipo_identificador}:{self.valor}>"