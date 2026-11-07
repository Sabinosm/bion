from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Paciente(db.Model):
    __tablename__ = "paciente"

    id = db.Column("id_paciente", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column(
        "uuid_paciente",
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    identificacao_anonima = db.Column(db.String(64))
    bairro = db.Column(db.String(100))
    sexo_biologico = db.Column(db.Enum("M", "F", "I"), nullable=False)
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"), nullable=False)
    data_nascimento = db.Column(db.Date)
    id_regiao_geografica = db.Column(
        db.BigInteger, db.ForeignKey("regiao_geografica.id_regiao_geografica")
    )
    data_primeiro_atendimento = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum("ativo", "inativo", "obito"), nullable=False, default="ativo")
    falecido = db.Column(db.Boolean, nullable=False, default=False)
    data_obito = db.Column(db.Date, nullable=True)
    nao_identificado = db.Column(db.Boolean, nullable=False, default=False)
    peso = db.Column(db.Float, nullable=True)
    altura = db.Column(db.Integer, nullable=True)
    criado_em = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    cadastrado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))

    empresa = db.relationship("Empresa", back_populates="pacientes")
    usuario_cadastro = db.relationship("Usuario", foreign_keys=[cadastrado_por])
    regiao_geografica = db.relationship("RegiaoGeografica", back_populates="pacientes")
    pessoal = db.relationship(
        "PacienteDadosPessoais",
        back_populates="paciente",
        uselist=False,
        cascade="all, delete-orphan",
    )
    observacoes_tipo_sanguineo = db.relationship(
        "ObservacaoTipoSanguineo",
        back_populates="paciente",
        cascade="save-update, merge",
        passive_deletes="all",
        order_by="desc(ObservacaoTipoSanguineo.data_registro), desc(ObservacaoTipoSanguineo.id)",
    )
    alergias = db.relationship(
        "Alergia", back_populates="paciente", cascade="save-update, merge", passive_deletes="all"
    )
    doencas = db.relationship(
        "DoencaCronica",
        back_populates="paciente",
        cascade="save-update, merge",
        passive_deletes="all",
    )
    medicamentos_em_uso = db.relationship(
        "MedicamentoEmUso", back_populates="paciente", cascade="all, delete-orphan"
    )
    consentimentos = db.relationship(
        "Consentimento", back_populates="paciente", cascade="all, delete-orphan"
    )
    consultas = db.relationship("Consulta", back_populates="paciente")

    @property
    def tipo_sanguineo(self):
        obs = self.observacoes_tipo_sanguineo[0] if self.observacoes_tipo_sanguineo else None
        return obs.tipo_sanguineo if obs else None

    def registrar_tipo_sanguineo(
        self, valor: str, registrado_por: int = None, id_atendimento_origem: int = None
    ):
        from src.models.pacientes.observacao_tipo_sanguineo import ObservacaoTipoSanguineo

        nova = ObservacaoTipoSanguineo(
            tipo_sanguineo=valor,
            registrado_por=registrado_por,
            id_atendimento_origem=id_atendimento_origem,
        )
        self.observacoes_tipo_sanguineo.insert(0, nova)

    def esta_falecido(self) -> bool:
        return bool(self.falecido) or self.status == "obito"

    def esta_anonimizado(self):
        return self.pessoal is None and not self.nao_identificado

    def pode_receber_atendimento(self) -> bool:
        if self.status == "obito":
            return False
        if getattr(self, "falecido", False):
            return False
        if getattr(self, "data_obito", None) is not None:
            return False
        return True

    def anonimizar(self, cpf_plaintext: str):
        from src.core.security import hmac_sha256

        self.identificacao_anonima = hmac_sha256(cpf_plaintext)
        self.pessoal = None

    def to_dict(self, incluir_pessoal=False):
        d = {
            "uuid": self.uuid,
            "sexo_biologico": self.sexo_biologico,
            "peso": self.peso,
            "altura": self.altura,
            "tipo_sanguineo": self.tipo_sanguineo,
            "data_nascimento": self.data_nascimento.isoformat() if self.data_nascimento else None,
            "status": self.status,
            "data_primeiro_atendimento": (
                self.data_primeiro_atendimento.isoformat()
                if self.data_primeiro_atendimento
                else None
            ),
            "nao_identificado": self.nao_identificado,
            "falecido": self.falecido,
            "data_obito": self.data_obito.isoformat() if self.data_obito else None,
            "cadastrado_por": (
                self.usuario_cadastro.nome_completo if self.usuario_cadastro else None
            ),
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }
        if incluir_pessoal and self.pessoal:
            d["pessoal"] = self.pessoal.to_dict()
        return d

    def to_dict_few(self, nome_completo: str = None, cpf_inicio: str = None):
        return {
            "uuid": self.uuid,
            "nome_completo": nome_completo,
            "cpf_inicio": cpf_inicio,
            "cadastrado_por": (
                self.usuario_cadastro.nome_completo if self.usuario_cadastro else None
            ),
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "sexo_biologico": self.sexo_biologico,
            "peso": self.peso,
            "altura": self.altura,
            "status": self.status,
            "nao_identificado": self.nao_identificado,
        }

    def __repr__(self):
        return f"<Paciente {self.uuid}>"
