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
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
 
    regiao_geografica = db.relationship("RegiaoGeografica", back_populates="empresas")
    usuarios = db.relationship("Usuario", back_populates="empresa",
                                cascade="all, delete-orphan")
    identificadores = db.relationship("EmpresaIdentificador", back_populates="empresa",
                                       cascade="all, delete-orphan")
    # NOVO: contrapartida de Paciente.empresa (back_populates="pacientes").
    # Sem esse lado declarado aqui, o SQLAlchemy levanta
    # InvalidRequestError ("Mapper[Empresa] has no property 'pacientes'")
    # assim que qualquer mapper é configurado, porque Paciente já
    # referenciava esse nome e o par não existia.
    #
    # Sem cascade delete-orphan de propósito: apagar uma Empresa não
    # deve apagar Paciente em cascata (dado clínico é sensível demais
    # pra depender de um DELETE de empresa; isso deve ser uma decisão
    # explícita/auditada, não um efeito colateral do ORM).
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

    def definir_cnes(self, valor: str):
        """Cria ou atualiza o identificador de CNES desta empresa.

        Mesma lógica de `definir_cnpj`: o service (não o model) é
        responsável por checar duplicidade contra outras empresas ANTES
        de chamar este método -- o model só grava, não decide se pode.
        Diferente do CNPJ, CNES é opcional -- este método só é chamado
        quando o valor foi de fato informado no cadastro.
        """
        ident = next((i for i in self.identificadores if i.tipo_identificador == "cnes"), None)
        if ident:
            ident.valor = valor
        else:
            from src.models.corp.empresa_identificador import EmpresaIdentificador
            self.identificadores.append(
                EmpresaIdentificador(tipo_identificador="cnes", valor=valor)
            )

    def to_dict(self):
        return {
               "uuid": self.uuid,
               "nome_fantasia": self.nome_fantasia,
               "razao_social": self.razao_social,
               # Agrupando os dados de endereço/região local
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