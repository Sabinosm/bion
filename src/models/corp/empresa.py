from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Empresa(db.Model):
    __tablename__ = "empresas"

    id = db.Column("id_empresa", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_empresa",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    nome_fantasia = db.Column(db.String(255), nullable=False)
    razao_social = db.Column(db.String(255))
    numero = db.Column(db.String(50))
    bairro = db.Column(db.String(100))
    complemento = db.Column(db.String(150))
    cep = db.Column(db.String(20))
    id_regiao_geografica = db.Column(
        db.BigInteger, db.ForeignKey("regiao_geografica.id_regiao_geografica")
    )
    status_plano = db.Column(db.String(50))
    plano = db.Column(db.String(100))
    dpo_nome = db.Column(db.String(255), nullable=True)
    dpo_email = db.Column(db.String(255), nullable=True)
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    regiao_geografica = db.relationship("RegiaoGeografica", back_populates="empresas")
    usuarios = db.relationship("Usuario", back_populates="empresa", cascade="all, delete-orphan")
    identificadores = db.relationship(
        "EmpresaIdentificador", back_populates="empresa", cascade="all, delete-orphan"
    )
    pacientes = db.relationship("Paciente", back_populates="empresa")

    def _identificador(self, tipo):
        return next((i for i in self.identificadores if i.tipo_identificador == tipo), None)

    def _definir_identificador(self, tipo, valor):
        ident = self._identificador(tipo)
        if ident:
            ident.valor = valor
            return
        from src.models.corp.empresa_identificador import EmpresaIdentificador

        self.identificadores.append(EmpresaIdentificador(tipo_identificador=tipo, valor=valor))

    @property
    def _uf(self):
        return self.regiao_geografica.uf if self.regiao_geografica else None

    @property
    def cnpj(self):
        ident = self._identificador("cnpj")
        return ident.valor if ident else None

    @property
    def cnes(self):
        ident = self._identificador("cnes")
        return ident.valor if ident else None

    def definir_cnpj(self, valor: str):
        self._definir_identificador("cnpj", valor)

    def definir_cnes(self, valor: str):
        self._definir_identificador("cnes", valor)

    @property
    def fuso_horario(self):
        from src.core.fusos_brasil import fuso_por_uf

        return fuso_por_uf(self._uf)

    @property
    def offset_horario(self) -> str:
        from src.core.fusos_brasil import offset_str_por_uf

        return offset_str_por_uf(self._uf)

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome_fantasia": self.nome_fantasia,
            "razao_social": self.razao_social,
            "dpo_nome": self.dpo_nome,
            "dpo_email": self.dpo_email,
            "endereco": {
                "cep": self.cep,
                "bairro": self.bairro,
                "numero": self.numero,
                "complemento": self.complemento,
            },
            "cnpj": self.cnpj,
            "cnes": self.cnes,
            "status_plano": self.status_plano,
            "plano": self.plano,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }
