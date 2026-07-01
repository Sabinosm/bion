"""
Regras de negocio do dominio Atendimento (Consultas e Triagem).

CORRECOES APLICADAS:
- `consulta/controller.py` original chamava `_svc.encerrar(uuid, desfecho, 1)`,
  mas `ConsultaService` nunca teve esse metodo -- so `buscar_por_uuid` e
  `listar`. Implementado aqui.
- `atendimento/controller.py` original tinha rotas `abrir_triagem`,
  `abrir_medico`, `registrar_sinais` e `finalizar` que so faziam
  flash + redirect, sem nenhuma chamada de service -- nada era
  persistido de fato. Implementadas aqui com logica real (criação de
  Atendimento, ColetaClinica, SinalVital, ResultadoPrescricao).
"""

from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from .repositories import (
    ConsultaRepository, AtendimentoRepository, ColetaClinicaRepository,
    SinalVitalRepository, InputProtocoloRepository, ResultadoPrescricaoRepository,
    PrescricaoRepository, PrescricaoExameRepository,
)


class ConsultaService:

    def __init__(self):
        self.repo = ConsultaRepository()

    def buscar_por_uuid(self, uuid: str):
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid}")
        return e

    def listar(self, apenas_abertas: bool = False):
        if apenas_abertas:
            return self.repo.find_abertas()
        return self.repo.find_all()

    def listar_por_paciente(self, id_paciente: int):
        return self.repo.find_por_paciente(id_paciente)

    def abrir(self, uuid_paciente: str, dados: dict, id_usuario: int):
        from src.database.clinico import Consulta
        from src.domains.paciente.repositories import PacienteRepository

        paciente = PacienteRepository().find_by_uuid(uuid_paciente)
        if not paciente:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")

        c = Consulta(
            id_paciente=paciente.id,
            tipo_consulta=dados.get("tipo_consulta", "triagem"),
            origem_encaminhamento=dados.get("origem_encaminhamento", "espontanea"),
            status_consulta="aguardando-triagem",
            data_hora_inicio=datetime.now(timezone.utc),
            iniciada_por=id_usuario,
        )
        return self.repo.save(c)

    def encerrar(self, uuid: str, desfecho: str, id_usuario: int):
        c = self.buscar_por_uuid(uuid)
        if c.status_consulta == "encerrada":
            raise ConflictoError("Consulta já está encerrada.")
        desfechos_validos = ("alta", "internacao", "transferencia", "obito", "evasao")
        if desfecho not in desfechos_validos:
            raise DadosInvalidosError(f"Desfecho inválido. Use um de: {', '.join(desfechos_validos)}")

        c.status_consulta = "encerrada"
        c.desfecho_final = desfecho
        c.data_hora_fim = datetime.now(timezone.utc)
        c.finalizada_por = id_usuario
        return self.repo.save(c)


class AtendimentoService:

    def __init__(self):
        self.repo = AtendimentoRepository()
        self.coleta_repo = ColetaClinicaRepository()
        self.sinal_repo = SinalVitalRepository()
        self.consulta_repo = ConsultaRepository()

    def buscar_por_uuid(self, uuid: str):
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid}")
        return e

    def listar(self):
        return self.repo.find_all()

    def listar_por_consulta(self, uuid_consulta: str):
        c = self.consulta_repo.find_by_uuid(uuid_consulta)
        if not c:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid_consulta}")
        return self.repo.find_por_consulta(c.id)

    def abrir_triagem(self, uuid_consulta: str, id_usuario: int):
        from src.database.clinico import Atendimento
        c = self.consulta_repo.find_by_uuid(uuid_consulta)
        if not c:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid_consulta}")

        atendimento = Atendimento(
            id_consulta=c.id,
            tipo_atendimento="triagem",
            realizado_por=id_usuario,
            status="em-andamento",
            data_hora_inicio=datetime.now(timezone.utc),
        )
        self.repo.save(atendimento)

        c.status_consulta = "em-triagem"
        self.consulta_repo.save(c)
        return atendimento

    def abrir_avaliacao_medica(self, uuid_consulta: str, id_usuario: int):
        from src.database.clinico import Atendimento
        c = self.consulta_repo.find_by_uuid(uuid_consulta)
        if not c:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid_consulta}")

        atendimento = Atendimento(
            id_consulta=c.id,
            tipo_atendimento="avaliacao-medica",
            realizado_por=id_usuario,
            status="em-andamento",
            data_hora_inicio=datetime.now(timezone.utc),
        )
        self.repo.save(atendimento)

        c.status_consulta = "em-atendimento"
        self.consulta_repo.save(c)
        return atendimento

    def registrar_sinais_vitais(self, uuid_atendimento: str, lista_sinais: list, id_usuario: int):
        from src.database.clinico import SinalVital
        atendimento = self.buscar_por_uuid(uuid_atendimento)
        if not lista_sinais:
            raise DadosInvalidosError("Informe ao menos um sinal vital.")

        registrados = []
        for s in lista_sinais:
            obrigatorios = ("tipo_parametro", "valor_numerico", "unidade")
            faltando = [c for c in obrigatorios if s.get(c) is None]
            if faltando:
                raise DadosInvalidosError(
                    f"Campos obrigatórios ausentes em sinal vital: {', '.join(faltando)}"
                )
            sv = SinalVital(
                id_atendimento=atendimento.id,
                tipo_parametro=s["tipo_parametro"],
                valor_numerico=s["valor_numerico"],
                unidade=s["unidade"],
                sitio_medicao=s.get("sitio_medicao"),
                data_hora_medicao=datetime.now(timezone.utc),
                coletado_por=id_usuario,
                flag_validacao_faixa=s.get("flag_validacao_faixa", "dentro-do-limite"),
                flag_escala_dpoc=bool(s.get("flag_escala_dpoc", False)),
            )
            self.sinal_repo.save(sv)
            registrados.append(sv)
        return registrados

    def registrar_coleta_clinica(self, uuid_atendimento: str, dados: dict):
        from src.database.clinico import ColetaClinica
        atendimento = self.buscar_por_uuid(uuid_atendimento)
        coleta = ColetaClinica(
            id_atendimento=atendimento.id,
            desde_quando_sintomas=dados.get("desde_quando_sintomas"),
        )
        return self.coleta_repo.save(coleta)

    def registrar_input_protocolo(self, uuid_coleta: str, dados: dict):
        from src.database.clinico import InputProtocolo
        coleta = self.coleta_repo.find_by_uuid(uuid_coleta)
        if not coleta:
            raise RecursoNaoEncontradoError(f"Coleta clínica não encontrada: {uuid_coleta}")

        ip = InputProtocolo(
            id_coleta_clinica=coleta.id,
            tipo_input=dados.get("tipo_input", "triagem"),
            input_json=dados.get("input_json"),
            queixa_principal=dados.get("queixa_principal"),
            valor_avpu=dados.get("valor_avpu"),
            dados_criticos_ausentes_json=dados.get("dados_criticos_ausentes"),
        )
        from src.database import db
        db.session.add(ip)
        db.session.commit()
        return ip

    def finalizar(self, uuid_atendimento: str, observacoes: str = None):
        atendimento = self.buscar_por_uuid(uuid_atendimento)
        if atendimento.status == "finalizado":
            raise ConflictoError("Atendimento já está finalizado.")
        atendimento.status = "finalizado"
        atendimento.data_hora_fim = datetime.now(timezone.utc)
        if observacoes:
            atendimento.observacoes_profissional = observacoes
        return self.repo.save(atendimento)


class PrescricaoService:
    """Registro do resultado clínico de um atendimento (diagnóstico +
    condutas): ResultadoPrescricao, Prescricao (medicamentos) e
    PrescricaoExame."""

    def __init__(self):
        self.resultado_repo = ResultadoPrescricaoRepository()
        self.prescricao_repo = PrescricaoRepository()
        self.exame_repo = PrescricaoExameRepository()
        self.atendimento_repo = AtendimentoRepository()

    def registrar_resultado(self, uuid_atendimento: str, dados: dict, id_usuario: int):
        from src.database.clinico import ResultadoPrescricao
        atendimento = self.atendimento_repo.find_by_uuid(uuid_atendimento)
        if not atendimento:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")

        obrigatorios = ("codigo_cid10_principal", "descricao_cid10_principal", "certeza_diagnostica")
        faltando = [c for c in obrigatorios if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")

        resultado = ResultadoPrescricao(
            id_atendimento=atendimento.id,
            id_output=dados.get("id_output"),
            codigo_cid10_principal=dados["codigo_cid10_principal"],
            descricao_cid10_principal=dados["descricao_cid10_principal"],
            certeza_diagnostica=dados["certeza_diagnostica"],
            tipo_prescricao=dados.get("tipo_prescricao"),
            consistente_com_classificacao=dados.get("consistente_com_classificacao"),
            formulado_por=id_usuario,
            data_hora_formulacao=datetime.now(timezone.utc),
        )
        return self.resultado_repo.save(resultado)

    def adicionar_medicamento(self, uuid_resultado: str, dados: dict):
        from src.database.clinico import Prescricao
        resultado = self.resultado_repo.find_by_uuid(uuid_resultado)
        if not resultado:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid_resultado}")

        p = Prescricao(
            id_resultado_prescricao=resultado.id,
            id_catalogo=dados.get("id_catalogo"),
            dose=dados.get("dose"),
            frequencia=dados.get("frequencia"),
            duracao=dados.get("duracao"),
            orientacoes=dados.get("orientacoes"),
        )
        return self.prescricao_repo.save(p)

    def adicionar_exame(self, uuid_resultado: str, dados: dict):
        from src.database.clinico import PrescricaoExame
        resultado = self.resultado_repo.find_by_uuid(uuid_resultado)
        if not resultado:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid_resultado}")

        pe = PrescricaoExame(
            id_resultado=resultado.id,
            id_exame=dados.get("id_exame"),
            urgencia=dados.get("urgencia", "rotina"),
            justificativa=dados.get("justificativa"),
            origem_sugestao=dados.get("origem_sugestao", "medico"),
            id_output_origem=dados.get("id_output_origem"),
        )
        return self.exame_repo.save(pe)

    def buscar_resultado_por_uuid(self, uuid: str):
        r = self.resultado_repo.find_by_uuid(uuid)
        if not r:
            raise RecursoNaoEncontradoError(f"Resultado de prescrição não encontrado: {uuid}")
        return r
