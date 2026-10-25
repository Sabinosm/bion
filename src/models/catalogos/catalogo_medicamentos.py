from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK

class CatalogoMedicamentos(db.Model):
    __tablename__ = "catalogo_medicamentos"
    __table_args__ = (
        # principio_ativo é o campo mais buscado (join com prescrição,
        # busca do médico)
        db.Index("idx_catalogo_principio_ativo", "principio_ativo"),
        # Chave de cruzamento entre fontes externas (ANVISA x Detecta):
        # nome sem acento, minúsculo e sem prefixo de sal. Único para
        # que a sincronização nunca crie o mesmo princípio ativo duas
        # vezes. NULL é permitido (linhas antigas antes do seed).
        db.UniqueConstraint("principio_ativo_normalizado",
                            name="uq_catalogo_principio_normalizado"),
    )

    id = db.Column("id_catalogo_medicamentos",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_catalogo_medicamentos",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    principio_ativo = db.Column(db.String(255))
    principio_ativo_normalizado = db.Column(db.String(255))
    classe_farmaceutica = db.Column(db.String(255))
    nomes_comerciais_json = db.Column(db.JSON)

    # Rastreabilidade: de onde veio o registro e quando foi checado
    # pela última vez contra essa fonte. A sincronização automática
    # aplica as mudanças direto; o antes/depois de cada alteração fica
    # em LogSincronizacaoCatalogo.
    fonte_origem = db.Column(db.String(255))
    ultima_verificacao_em = db.Column(db.DateTime(timezone=True))

    medicamentos_em_uso = db.relationship("MedicamentoEmUso", back_populates="catalogo_medicamentos")
    prescricoes = db.relationship("Prescricao", back_populates="catalogo_medicamentos")
    interacoes_como_a = db.relationship(
        "InteracoesMedicamentos", foreign_keys="InteracoesMedicamentos.id_medicamento_a",
        back_populates="medicamento_a")
    interacoes_como_b = db.relationship(
        "InteracoesMedicamentos", foreign_keys="InteracoesMedicamentos.id_medicamento_b",
        back_populates="medicamento_b")
    indicacoes_terapeuticas = db.relationship(
        "IndicacaoTerapeutica", secondary="catalogo_medicamentos_indicacoes",
        back_populates="medicamentos")
    contraindicacoes = db.relationship(
        "Contraindicacao", secondary="catalogo_medicamentos_contraindicacoes",
        back_populates="medicamentos")
    sinonimos = db.relationship("CatalogoMedicamentosSinonimo", back_populates="catalogo_medicamentos")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "principio_ativo": self.principio_ativo,
            "classe_farmaceutica": self.classe_farmaceutica,
            "nomes_comerciais": self.nomes_comerciais_json,
            "fonte_origem": self.fonte_origem,
            "ultima_verificacao_em": self.ultima_verificacao_em.isoformat()
            if self.ultima_verificacao_em else None,
            "indicacoes_terapeuticas": [i.nome for i in self.indicacoes_terapeuticas],
            "contraindicacoes": [c.nome for c in self.contraindicacoes],
        }

    def __repr__(self):
        return f"<CatalogoMedicamentos {self.uuid} [{self.principio_ativo}]>"

    def to_dict_resumo(self):
        """Para listas: sem relacionamentos, evitando uma consulta extra por linha."""
        return {
            "uuid": self.uuid,
            "principio_ativo": self.principio_ativo,
            "classe_farmaceutica": self.classe_farmaceutica,
            "nomes_comerciais": self.nomes_comerciais_json,
        }

    def to_dict_detalhe(self):
        d = self.to_dict_resumo()
        d.update({
            "indicacoes_terapeuticas": [
                {"uuid": i.uuid, "nome": i.nome}
                for i in sorted(self.indicacoes_terapeuticas, key=lambda i: i.nome)],
            "contraindicacoes": [
                {"uuid": c.uuid, "nome": c.nome, "descricao": c.descricao}
                for c in sorted(self.contraindicacoes, key=lambda c: c.nome)],
            "fonte_origem": self.fonte_origem,
            "ultima_verificacao_em": self.ultima_verificacao_em.isoformat()
            if self.ultima_verificacao_em else None,
        })
        return d

class CatalogoMedicamentosSinonimo(db.Model):
    """Nome alternativo (já normalizado) que aponta para um item do
    catálogo -- cobre os casos que normalizar_nome() não resolve sozinho
    (ex: nome em inglês, grafia diferente entre ANVISA e Detecta).
    Curadoria manual, idealmente revisada por alguém da área da saúde."""
    __tablename__ = "catalogo_medicamentos_sinonimos"

    id = db.Column("id_sinonimo", BigIntPK, primary_key=True, autoincrement=True)
    id_catalogo = db.Column(db.BigInteger,
        db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos"), nullable=False)
    nome_normalizado = db.Column(db.String(255), nullable=False, unique=True)
    fonte = db.Column(db.String(100))

    catalogo_medicamentos = db.relationship("CatalogoMedicamentos", back_populates="sinonimos")