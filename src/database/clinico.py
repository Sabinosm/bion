"""
Dominio Clinico (nucleo do ciclo de vida do atendimento/visita).

Consulta, Atendimento e SinalVital ja estavam completos no projeto
original. ColetaClinica, ResultadoPrescricao, InputProtocolo,
InputProtocoloExecucao, Prescricao e PrescricaoExame eram stubs ou nem
existiam como classe -- completados aqui com os campos do schema.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.database import db
from src.database.types import BigIntPK


class Consulta(db.Model):
    __tablename__ = "consulta"

    id = db.Column("id_consulta",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_consulta",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_paciente = db.Column("id_paciente",db.BigInteger, db.ForeignKey("paciente.id_paciente"), nullable=False)
    tipo_consulta = db.Column(db.Enum("triagem", "consulta-medica"), nullable=False)
    origem_encaminhamento = db.Column(
        db.Enum("espontanea", "SAMU", "transferencia", "regulacao"),
        nullable=False, default="espontanea")
    status_consulta = db.Column(
        db.Enum("aguardando-triagem", "em-triagem", "aguardando-medico",
                "em-atendimento", "em-observacao", "encerrada"),
        nullable=False, default="aguardando-triagem")
    data_hora_inicio = db.Column(db.DateTime(timezone=True), nullable=False,
                                  default=lambda: datetime.now(timezone.utc))
    data_hora_fim = db.Column(db.DateTime(timezone=True))
    desfecho_final = db.Column(
        db.Enum("alta", "internacao", "transferencia", "obito", "evasao"))
    iniciada_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    finalizada_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    paciente = db.relationship("Paciente", back_populates="consultas")
    usuario_iniciou = db.relationship("Usuario", foreign_keys=[iniciada_por])
    usuario_finalizou = db.relationship("Usuario", foreign_keys=[finalizada_por])
    atendimentos = db.relationship("Atendimento", back_populates="consulta",
                                    cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_consulta": self.tipo_consulta,
            "origem_encaminhamento": self.origem_encaminhamento,
            "status_consulta": self.status_consulta,
            "data_hora_inicio": self.data_hora_inicio.isoformat() if self.data_hora_inicio else None,
            "data_hora_fim": self.data_hora_fim.isoformat() if self.data_hora_fim else None,
            "desfecho_final": self.desfecho_final,
            "paciente_uuid": self.paciente.uuid if self.paciente else None,
        }

    def __repr__(self):
        return f"<Consulta {self.uuid} [{self.status_consulta}]>"


class Atendimento(db.Model):
    __tablename__ = "atendimento"

    id = db.Column("id_atendimento",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_atendimento",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_consulta = db.Column(db.BigInteger, db.ForeignKey("consulta.id_consulta"), nullable=False)
    tipo_atendimento = db.Column(
        db.Enum("triagem", "avaliacao-medica", "reavaliacao", "alta", "procedimento"),
        nullable=False)
    realizado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    status = db.Column(db.Enum("em-andamento", "finalizado", "cancelado"),
                        nullable=False, default="em-andamento")
    data_hora_inicio = db.Column(db.DateTime(timezone=True), nullable=False,
                                  default=lambda: datetime.now(timezone.utc))
    data_hora_fim = db.Column(db.DateTime(timezone=True))
    habitos_atendimento_json = db.Column(db.JSON)
    observacoes_profissional = db.Column(db.Text)

    consulta = db.relationship("Consulta", back_populates="atendimentos")
    usuario = db.relationship("Usuario")
    coletas_clinicas = db.relationship("ColetaClinica", back_populates="atendimento",
                                        cascade="all, delete-orphan")
    resultados_prescricao = db.relationship("ResultadoPrescricao", back_populates="atendimento",
                                             cascade="all, delete-orphan")
    sinais_vitais = db.relationship("SinalVital", back_populates="atendimento",
                                     cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_atendimento": self.tipo_atendimento,
            "status": self.status,
            "data_hora_inicio": self.data_hora_inicio.isoformat() if self.data_hora_inicio else None,
            "data_hora_fim": self.data_hora_fim.isoformat() if self.data_hora_fim else None,
            "observacoes_profissional": self.observacoes_profissional,
            "consulta_uuid": self.consulta.uuid if self.consulta else None,
        }

    def __repr__(self):
        return f"<Atendimento {self.uuid} [{self.tipo_atendimento}]>"


class ColetaClinica(db.Model):
    __tablename__ = "coleta_clinica"

    id = db.Column("id_coleta",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_coleta",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_atendimento = db.Column(db.BigInteger, db.ForeignKey("atendimento.id_atendimento"), nullable=False)
    desde_quando_sintomas = db.Column(db.SmallInteger)  # horas

    atendimento = db.relationship("Atendimento", back_populates="coletas_clinicas")
    inputs_protocolo = db.relationship("InputProtocolo", back_populates="coleta_clinica",
                                        cascade="all, delete-orphan")

    def to_dict(self):
        return {"uuid": self.uuid, "desde_quando_sintomas": self.desde_quando_sintomas}

    def __repr__(self):
        return f"<ColetaClinica {self.uuid}>"


class SinalVital(db.Model):
    __tablename__ = "sinal_vital"

    id = db.Column("id_sinal_vital",BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_sinal_vital",db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_atendimento = db.Column(db.BigInteger, db.ForeignKey("atendimento.id_atendimento"), nullable=False)
    tipo_parametro = db.Column(
        db.Enum("frequencia-respiratoria", "spo2", "pa-sistolica", "pa-diastolica",
                "frequencia-cardiaca", "temperatura", "glicemia-capilar"),
        nullable=False)
    valor_numerico = db.Column(db.Numeric(10, 2), nullable=False)
    unidade = db.Column(
        db.Enum("irpm", "%", "mmHg", "bpm", "°C", "mg-dL"), nullable=False)
    sitio_medicao = db.Column(
        db.Enum("axilar", "oral", "retal", "timpanico", "oximetria-digital",
                "manguito-braco-direito", "manguito-braco-esquerdo"))
    data_hora_medicao = db.Column(db.DateTime(timezone=True), nullable=False,
                                   default=lambda: datetime.now(timezone.utc))
    coletado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    flag_validacao_faixa = db.Column(
        db.Enum("dentro-do-limite", "fora-limite-alertado", "fora-limite-rejeitado"),
        nullable=False, default="dentro-do-limite")
    flag_escala_dpoc = db.Column(db.Boolean, nullable=False, default=False)

    atendimento = db.relationship("Atendimento", back_populates="sinais_vitais")
    usuario = db.relationship("Usuario")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_parametro": self.tipo_parametro,
            "valor_numerico": float(self.valor_numerico) if self.valor_numerico is not None else None,
            "unidade": self.unidade,
            "sitio_medicao": self.sitio_medicao,
            "data_hora_medicao": self.data_hora_medicao.isoformat() if self.data_hora_medicao else None,
            "flag_validacao_faixa": self.flag_validacao_faixa,
        }

    def __repr__(self):
        return f"<SinalVital {self.uuid} [{self.tipo_parametro}={self.valor_numerico}]>"


class InputProtocolo(db.Model):
    __tablename__ = "input_protocolo"

    id = db.Column("id_input", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_input", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_coleta_clinica = db.Column(db.BigInteger, db.ForeignKey("coleta_clinica.id_coleta"))
    tipo_input = db.Column(db.Enum("triagem", "consulta"))
    input_json = db.Column(db.JSON)
    queixa_principal = db.Column(db.Text)
    valor_avpu = db.Column(db.String(20))
    dados_criticos_ausentes_json = db.Column(db.JSON)

    coleta_clinica = db.relationship("ColetaClinica", back_populates="inputs_protocolo")
    outputs = db.relationship("OutputBion", back_populates="input_protocolo")
    execucoes = db.relationship("InputProtocoloExecucao", back_populates="input_protocolo",
                                 cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "tipo_input": self.tipo_input,
            "input": self.input_json,
            "queixa_principal": self.queixa_principal,
            "valor_avpu": self.valor_avpu,
        }

    def __repr__(self):
        return f"<InputProtocolo {self.uuid}>"


class InputProtocoloExecucao(db.Model):
    __tablename__ = "input_protocolo_execucao"

    id = db.Column("id_input_execucao",BigIntPK, primary_key=True, autoincrement=True)
    id_input = db.Column(db.BigInteger, db.ForeignKey("input_protocolo.id_input"))
    id_protocolo_catalogo = db.Column(db.BigInteger, db.ForeignKey("protocolo_catalogo.id_protocolo_catalogo"))

    input_protocolo = db.relationship("InputProtocolo", back_populates="execucoes")
    protocolo_catalogo = db.relationship("ProtocoloCatalogo", back_populates="execucoes")

    def __repr__(self):
        return f"<InputProtocoloExecucao {self.id}>"


class ResultadoPrescricao(db.Model):
    __tablename__ = "resultado_prescricao"

    id = db.Column("id_resultado", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_resultado", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_atendimento = db.Column(db.BigInteger, db.ForeignKey("atendimento.id_atendimento"), nullable=False)
    id_output = db.Column(db.BigInteger, db.ForeignKey("output_bion.id_output"))
    codigo_cid10_principal = db.Column(db.String(10), nullable=False)
    descricao_cid10_principal = db.Column(db.String(255), nullable=False)
    certeza_diagnostica = db.Column(
        db.Enum("suspeito", "provavel", "confirmado", "descartado"), nullable=False)
    tipo_prescricao = db.Column(
        db.Enum("farmacologica", "nao-farmacologica", "encaminhamento", "internacao", "alta"))
    consistente_com_classificacao = db.Column(db.Boolean)
    formulado_por = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=False)
    data_hora_formulacao = db.Column(db.DateTime(timezone=True), nullable=False,
                                      default=lambda: datetime.now(timezone.utc))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    atendimento = db.relationship("Atendimento", back_populates="resultados_prescricao")
    output_bion = db.relationship("OutputBion", back_populates="resultados_prescricao")
    usuario = db.relationship("Usuario")
    prescricoes = db.relationship("Prescricao", back_populates="resultado_prescricao",
                                   cascade="all, delete-orphan")
    prescricoes_exame = db.relationship("PrescricaoExame", back_populates="resultado_prescricao",
                                         cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "codigo_cid10_principal": self.codigo_cid10_principal,
            "descricao_cid10_principal": self.descricao_cid10_principal,
            "certeza_diagnostica": self.certeza_diagnostica,
            "tipo_prescricao": self.tipo_prescricao,
            "data_hora_formulacao": self.data_hora_formulacao.isoformat()
            if self.data_hora_formulacao else None,
        }

    def __repr__(self):
        return f"<ResultadoPrescricao {self.uuid} [{self.codigo_cid10_principal}]>"


class Prescricao(db.Model):
    __tablename__ = "prescricao"

    id = db.Column("id_prescricao", BigIntPK, primary_key=True, autoincrement=True)
    id_resultado_prescricao = db.Column(db.BigInteger, db.ForeignKey("resultado_prescricao.id_resultado"))
    id_catalogo = db.Column(db.BigInteger, db.ForeignKey("catalogo_medicamentos.id_catalogo_medicamento"))
    dose = db.Column(db.String(100))
    frequencia = db.Column(db.String(100))
    duracao = db.Column(db.String(100))
    orientacoes = db.Column(db.Text)

    resultado_prescricao = db.relationship("ResultadoPrescricao", back_populates="prescricoes")
    catalogo_medicamento = db.relationship("CatalogoMedicamentos", back_populates="prescricoes")

    def to_dict(self):
        return {
            "id": self.id,
            "dose": self.dose,
            "frequencia": self.frequencia,
            "duracao": self.duracao,
            "orientacoes": self.orientacoes,
            "medicamento": self.catalogo_medicamento.to_dict() if self.catalogo_medicamento else None,
        }

    def __repr__(self):
        return f"<Prescricao {self.id}>"


class PrescricaoExame(db.Model):
    __tablename__ = "prescricao_exame"

    id = db.Column("id_prescricao_exame", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_prescricao_exame", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_resultado = db.Column(db.BigInteger, db.ForeignKey("resultado_prescricao.id_resultado"))
    id_exame = db.Column(db.BigInteger, db.ForeignKey("catalogo_exames.id_catalogo_exame"))
    id_output_origem = db.Column(db.BigInteger, db.ForeignKey("output_bion.id_output"))
    urgencia = db.Column(db.Enum("rotina", "urgente", "emergencia"))
    justificativa = db.Column(db.Text)
    origem_sugestao = db.Column(db.Enum("medico", "bion_ia", "protocolo"))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    resultado_prescricao = db.relationship("ResultadoPrescricao", back_populates="prescricoes_exame")
    catalogo_exame = db.relationship("CatalogoExames", back_populates="prescricoes_exame")
    output_origem = db.relationship("OutputBion", back_populates="prescricoes_exame")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "urgencia": self.urgencia,
            "justificativa": self.justificativa,
            "origem_sugestao": self.origem_sugestao,
            "exame": self.catalogo_exame.to_dict() if self.catalogo_exame else None,
        }

    def __repr__(self):
        return f"<PrescricaoExame {self.uuid}>"
