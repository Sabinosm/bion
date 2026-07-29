"""
Dominio Corporativo / Regional.

ALTERADO: cnpj deixou de ser coluna direta -- agora vive em
EmpresaIdentificador (tipo_identificador='cnpj'), abrindo espaço para
CNES no futuro sem nova migração.

Mantida uma @property `cnpj` para que código existente que lê
`empresa.cnpj` continue funcionando sem alteração (mesmo padrão usado
em Usuario.tipo_usuario). ATENÇÃO: diferente de lá, aqui NÃO dá para
usar um setter de property com a mesma simplicidade porque criar/trocar
identificador envolve checar duplicidade -- por isso a ESCRITA de CNPJ
tem um método explícito (`definir_cnpj`), não um `empresa.cnpj = valor`.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Empresa(db.Model):
    __tablename__ = "empresa"

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
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    regiao_geografica = db.relationship("RegiaoGeografica", back_populates="empresas")
    usuarios = db.relationship("Usuario", back_populates="empresa",
                                cascade="all, delete-orphan")
    identificadores = db.relationship("EmpresaIdentificador", back_populates="empresa",
                                       cascade="all, delete-orphan")

    @property
    def cnpj(self):
        """Leitura de compatibilidade: `empresa.cnpj` continua funcionando
        como antes, sem parênteses, para todo código já existente."""
        ident = next((i for i in self.identificadores if i.tipo_identificador == "cnpj"), None)
        return ident.valor if ident else None

    def definir_cnpj(self, valor: str):
        """Cria ou atualiza o identificador de CNPJ desta empresa.

        Não é feito via `empresa.cnpj = valor` de propósito: diferente
        de uma coluna simples, isso é uma linha de outra tabela, e o
        service (não o model) é responsável por checar duplicidade
        contra outras empresas ANTES de chamar este método -- o model
        só grava, não decide se pode.
        """
        ident = next((i for i in self.identificadores if i.tipo_identificador == "cnpj"), None)
        if ident:
            ident.valor = valor
        else:
            from src.models.corp.empresa_identificador import EmpresaIdentificador
            self.identificadores.append(
                EmpresaIdentificador(tipo_identificador="cnpj", valor=valor)
            )

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nome_fantasia": self.nome_fantasia,
            "razao_social": self.razao_social,
            "cnpj": self.cnpj,
            "status_plano": self.status_plano,
            "plano": self.plano,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }

    