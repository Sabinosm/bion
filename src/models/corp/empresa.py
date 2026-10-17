"""
Dominio Corporativo / Regional.

ALTERADO: cnpj deixou de ser coluna direta -- agora vive em
EmpresaIdentificador (tipo_identificador='cnpj'), abrindo espaço para
CNES no futuro sem nova migração.

Mantida uma @property `cnpj` para que código existente que lê
`empresa.cnpj` continue funcionando sem alteração. a ESCRITA de CNPJ
tem um método explícito (`definir_cnpj`), não um `empresa.cnpj = valor`.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Empresa(db.Model):
    __tablename__ = "empresas"
 
    id = db.Column("id_empresa", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_empresa", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    nome_fantasia = db.Column(db.String(255), nullable=False)
    razao_social = db.Column(db.String(255))
    # cnpj REMOVIDO como coluna direta -- ver EmpresaIdentificador
    numero = db.Column(db.String(50))
    bairro = db.Column(db.String(100))
    complemento = db.Column(db.String(150))
    cep = db.Column(db.String(20))
    id_regiao_geografica = db.Column(db.BigInteger, db.ForeignKey("regiao_geografica.id_regiao_geografica"))
    status_plano = db.Column(db.String(50))
    plano = db.Column(db.String(100))
    dpo_nome = db.Column(db.String(255), nullable=True)
    dpo_email = db.Column(db.String(255), nullable=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
 
    regiao_geografica = db.relationship("RegiaoGeografica", back_populates="empresas")
    usuarios = db.relationship("Usuario", back_populates="empresa",
                                cascade="all, delete-orphan")
    identificadores = db.relationship("EmpresaIdentificador", back_populates="empresa",
                                       cascade="all, delete-orphan")
    pacientes = db.relationship("Paciente", back_populates="empresa")

    @property
    def cnpj(self):
        """Leitura de compatibilidade: `empresa.cnpj` continua funcionando
        como antes, sem parênteses, para todo código já existente."""
        ident = next((i for i in self.identificadores if i.tipo_identificador == "cnpj"), None)
        return ident.valor if ident else None

    @property
    def cnes(self):
        """Leitura do CNES, mesmo padrão da property `cnpj`. Pode ser
        None, já que CNES é opcional (nem toda empresa tem)."""
        ident = next((i for i in self.identificadores if i.tipo_identificador == "cnes"), None)
        return ident.valor if ident else None

    def definir_cnpj(self, valor: str):
        """Cria ou atualiza o identificador de CNPJ desta empresa."""
        ident = next((i for i in self.identificadores if i.tipo_identificador == "cnpj"), None)
        if ident:
            ident.valor = valor
        else:
            from src.models.corp.empresa_identificador import EmpresaIdentificador
            self.identificadores.append(
                EmpresaIdentificador(tipo_identificador="cnpj", valor=valor)
            )

    def definir_cnes(self, valor: str):
        """Cria ou atualiza o identificador de CNES desta empresa."""
        ident = next((i for i in self.identificadores if i.tipo_identificador == "cnes"), None)
        if ident:
            ident.valor = valor
        else:
            from src.models.corp.empresa_identificador import EmpresaIdentificador
            self.identificadores.append(
                EmpresaIdentificador(tipo_identificador="cnes", valor=valor)
            )

    @property
    def fuso_horario(self):
        """Fuso horário oficial da empresa, resolvido pela UF da
        região geográfica associada (ver src/core/fusos_brasil.py)."""
        from src.core.fusos_brasil import fuso_por_uf
        uf = self.regiao_geografica.uf if self.regiao_geografica else None
        return fuso_por_uf(uf)

    @property
    def offset_horario(self) -> str:
        """Offset fixo da empresa como string "+HH:MM"/"-HH:MM", para
        uso em CONVERT_TZ() do MySQL (ver src/core/fusos_brasil.py)."""
        from src.core.fusos_brasil import offset_str_por_uf
        uf = self.regiao_geografica.uf if self.regiao_geografica else None
        return offset_str_por_uf(uf)

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