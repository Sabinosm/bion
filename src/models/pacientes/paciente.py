"""
Dominio Paciente.

ALTERADO:
1. tipo_sanguineo REMOVIDO como coluna direta -- vira @property que lê
   da observação mais recente em ObservacaoTipoSanguineo. to_dict()
   continua expondo o mesmo valor, sem mudança perceptível pro front
   (decisão confirmada com o usuário).
2. anonimizar() CORRIGIDO: antes só gerava identificacao_anonima, mas
   não desligava PacientePessoal -- esta_anonimizado() nunca ficava
   True de fato. Agora remove a relação de verdade.
3. Campos falecido/data_obito adicionados (status='obito' ganha
   representação própria, equivalente a Patient.deceasedBoolean/
   deceasedDateTime do FHIR).
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Paciente(db.Model):
    __tablename__ = "paciente"

    id = db.Column("id_paciente", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_paciente", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    identificacao_anonima = db.Column(db.String(64))
    bairro = db.Column(db.String(100))
    sexo_biologico = db.Column(db.Enum("M", "F", "I"), nullable=False)

    # NOVO: posse do paciente. Explícito e imutável após a criação --
    # não inferido via cadastrado_por -> usuario.id_empresa (frágil:
    # usuário pode trocar de empresa ou ser removido depois).
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"), nullable=False)
    # tipo_sanguineo REMOVIDO como coluna -- ver property abaixo
    data_nascimento = db.Column(db.Date)
    id_regiao_geografica = db.Column(db.BigInteger, db.ForeignKey("regiao_geografica.id_regiao_geografica"))
    data_primeiro_atendimento = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum("ativo", "inativo", "obito"),
                        nullable=False, default="ativo")

    # NOVO: espelha Patient.deceasedBoolean/deceasedDateTime do FHIR
    falecido = db.Column(db.Boolean, nullable=False, default=False)
    data_obito = db.Column(db.Date, nullable=True)

    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)
    cadastrado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))

    empresa = db.relationship("Empresa", back_populates="pacientes")
    regiao_geografica = db.relationship("RegiaoGeografica", back_populates="pacientes")
    pessoal = db.relationship("PacienteDadosPessoais", back_populates="paciente",
                               uselist=False, cascade="all, delete-orphan")
    observacoes_tipo_sanguineo = db.relationship(
        "ObservacaoTipoSanguineo", back_populates="paciente",
        cascade="all, delete-orphan",
        order_by="desc(ObservacaoTipoSanguineo.data_registro)",
    )
    alergias = db.relationship("Alergia", back_populates="paciente",
                                cascade="all, delete-orphan")
    doencas = db.relationship("DoencaCronica", back_populates="paciente",
                               cascade="all, delete-orphan")
    medicamentos_em_uso = db.relationship("MedicamentoEmUso", back_populates="paciente",
                                           cascade="all, delete-orphan")
    consentimentos = db.relationship("Consentimento", back_populates="paciente",
                                      cascade="all, delete-orphan")
    consultas = db.relationship("Consulta", back_populates="paciente")

    @property
    def tipo_sanguineo(self):
        """Leitura de compatibilidade: `paciente.tipo_sanguineo` continua
        funcionando como antes (string simples), buscando internamente
        a observação mais recente em vez de uma coluna direta."""
        obs = self.observacoes_tipo_sanguineo[0] if self.observacoes_tipo_sanguineo else None
        return obs.tipo_sanguineo if obs else None

    def registrar_tipo_sanguineo(self, valor: str, registrado_por: int = None):
        """Cria uma nova observação de tipo sanguíneo.

        Não é feito via `paciente.tipo_sanguineo = valor` de propósito:
        diferente de uma coluna simples, isso é uma nova linha de
        histórico clínico (quem registrou, quando), não uma sobrescrita.
        """
        from src.models.pacientes.observacao_tipo_sanguineo import ObservacaoTipoSanguineo
        nova = ObservacaoTipoSanguineo(tipo_sanguineo=valor, registrado_por=registrado_por)
        self.observacoes_tipo_sanguineo.insert(0, nova)

    def esta_anonimizado(self):
        return self.pessoal is None

    def anonimizar(self, cpf_plaintext: str):
        """CORRIGIDO: antes só gerava identificacao_anonima, sem de fato
        remover PacienteDadosPessoais -- esta_anonimizado() nunca detectava
        a anonimização corretamente. Agora remove a relação de verdade,
        deixando o SQLAlchemy cuidar do DELETE via cascade já configurado.
        """
        from src.core.security import hmac_sha256
        self.identificacao_anonima = hmac_sha256(cpf_plaintext)
        self.pessoal = None  # aciona o cascade="all, delete-orphan" já existente

    def to_dict(self, incluir_pessoal=False):
        d = {
            "uuid": self.uuid,
            "sexo_biologico": self.sexo_biologico,
            "tipo_sanguineo": self.tipo_sanguineo,  # via property, comportamento idêntico a antes
            "data_nascimento": self.data_nascimento.isoformat() if self.data_nascimento else None,
            "status": self.status,
            "data_primeiro_atendimento": self.data_primeiro_atendimento.isoformat()
            if self.data_primeiro_atendimento else None,
        }
        if incluir_pessoal and self.pessoal:
            d["pessoal"] = self.pessoal.to_dict()
        return d


    def __repr__(self):
        return f"<Paciente {self.uuid}>"