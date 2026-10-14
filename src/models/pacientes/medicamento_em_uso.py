"""
Dominio Paciente.

Medicamento em uso do paciente (Bloco 2). Regras do modelo:

1. Histórico preservado, sem atualização no lugar: mudar dose/frequência
   = FECHAR o registro (status_uso, ate, encerrado_por,
   id_atendimento_encerramento) e CRIAR outro; o antigo aponta para o
   novo em id_substituida_por.
2. Dados novos nascem com criado_por e id_atendimento_origem (ficam NULL
   só nas linhas antigas, anteriores ao Bloco 2).
3. id_catalogo é opcional (medicamento fora do catálogo), mas descricao é
   sempre obrigatória. Sem id_catalogo o item NÃO entra na checagem de
   interações.
4. flag_em_uso foi removido. "Ativo" = status_uso='ativo' AND
   deletado=False (ver a propriedade `ativo`, que também serve em query).
5. `deletado` é separado de status_uso de propósito: "interrompido" ou
   "concluido" é estado clínico real do tratamento; "deletado" é "não
   devia existir esse registro" (duplicado, erro de digitação etc.).
   Soft delete guarda motivo, autor e atendimento.
"""

from datetime import datetime, timezone
import uuid as _uuid

from sqlalchemy.ext.hybrid import hybrid_property

from src.models import db
from src.models.types import BigIntPK

# Alvos das FKs de auditoria -- ajuste aqui se os nomes reais forem outros.
_FK_USUARIO = "usuarios.id_usuario"
_FK_ATENDIMENTO = "atendimento.id_atendimento"


class MedicamentoEmUso(db.Model):
    __tablename__ = "medicamentos_em_uso"
    __table_args__ = (
        db.Index("idx_medicamento_em_uso_deletado", "deletado"),
        db.Index("idx_medicamento_em_uso_paciente_deletado", "id_paciente", "deletado"),
    )

    id = db.Column("id_medicamento_uso", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_medicamentos_uso", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column(db.BigInteger,
                            db.ForeignKey("paciente.id_paciente", ondelete="RESTRICT"),
                            nullable=False)
    id_catalogo = db.Column(db.BigInteger,
                            db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamentos",
                                          ondelete="RESTRICT"),
                            nullable=True)
    descricao = db.Column(db.Text, nullable=False)
    dose = db.Column(db.String(100))
    frequencia = db.Column(db.String(100))
    desde = db.Column(db.Date)
    ate = db.Column(db.Date, nullable=True)
    status_uso = db.Column(db.Enum("ativo", "interrompido", "concluido"),
                           nullable=False, default="ativo", server_default="ativo")

    # Origem (quem registrou e em qual atendimento)
    criado_por = db.Column(db.BigInteger, db.ForeignKey(_FK_USUARIO, ondelete="RESTRICT"),
                           nullable=True)
    id_atendimento_origem = db.Column(db.BigInteger,
                                      db.ForeignKey(_FK_ATENDIMENTO, ondelete="RESTRICT"),
                                      nullable=True)

    # Encerramento clínico (fechar): quem fechou, em qual atendimento e,
    # se foi troca de dose/frequência, qual registro o substituiu.
    encerrado_por = db.Column(db.BigInteger, db.ForeignKey(_FK_USUARIO, ondelete="RESTRICT"),
                              nullable=True)
    id_atendimento_encerramento = db.Column(db.BigInteger,
                                            db.ForeignKey(_FK_ATENDIMENTO, ondelete="RESTRICT"),
                                            nullable=True)
    id_substituida_por = db.Column(db.BigInteger,
                                   db.ForeignKey("medicamentos_em_uso.id_medicamento_uso",
                                                 ondelete="RESTRICT"),
                                   nullable=True)

    # Soft delete (ver nota 5 no topo)
    deletado = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    deletado_em = db.Column(db.DateTime(timezone=True), nullable=True)
    motivo_delete = db.Column(
        db.Enum(
            "erro-digitacao",
            "registro-duplicado",
            "diagnostico-incorreto",
            "solicitacao-paciente",
            "outro",
        ),
        nullable=True,
    )
    observacoes_delete = db.Column(db.Text, nullable=True)
    deletado_por = db.Column(db.BigInteger, db.ForeignKey(_FK_USUARIO, ondelete="RESTRICT"),
                             nullable=True)
    id_atendimento_delecao = db.Column(db.BigInteger,
                                       db.ForeignKey(_FK_ATENDIMENTO, ondelete="RESTRICT"),
                                       nullable=True)

    paciente = db.relationship("Paciente", back_populates="medicamentos_em_uso")
    # Só leitura: usado para expor uuid_atendimento_origem (aviso de "veio de outro atendimento").
    atendimento_origem = db.relationship("Atendimento", foreign_keys=[id_atendimento_origem],
                                         viewonly=True)
    catalogo_medicamentos = db.relationship("CatalogoMedicamentos",
                                            back_populates="medicamentos_em_uso")

    @hybrid_property
    def ativo(self):
        return self.status_uso == "ativo" and not self.deletado

    @ativo.expression
    def ativo(cls):
        return db.and_(cls.status_uso == "ativo", cls.deletado == False)  # noqa: E712

    def to_dict(self):
        catalogo = self.catalogo_medicamentos
        return {
            "uuid": self.uuid,
            "descricao": self.descricao,
            "dose": self.dose,
            "frequencia": self.frequencia,
            "desde": self.desde.isoformat() if self.desde else None,
            "ate": self.ate.isoformat() if self.ate else None,
            "status_uso": self.status_uso,
            # permite ao front avisar que o dado veio de outro atendimento
            "uuid_atendimento_origem": self.atendimento_origem.uuid if self.atendimento_origem else None,
            "ativo": bool(self.ativo),
            "catalogo": {
                "uuid": catalogo.uuid,
                "principio_ativo": catalogo.principio_ativo,
            } if catalogo else None,
            # False = fora do catálogo: não entra na checagem de interações
            "verificavel_interacoes": self.id_catalogo is not None,
        }

    def __repr__(self):
        return f"<MedicamentoEmUso {self.uuid}>"
