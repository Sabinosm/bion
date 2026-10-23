"""
controller.py

Camada HTTP das estatísticas do Bion (dashboards). Todas as rotas são GET e
consultam os dados da empresa da sessão. O bloco operacional e as métricas de
versão do modelo e de correlação da IA exigem admin; as demais métricas de
qualidade da IA, o epidemiológico, a farmacovigilância e o histórico clínico
exigem apenas login, para que médicos e enfermeiros também acessem.
Os parâmetros opcionais (período em dias, limite de itens) vêm da query string
e são repassados ao service, que concentra o cálculo: valores que não sejam
inteiros são ignorados e vale o padrão de cada rota, e valores fora da faixa
permitida são rejeitados com erro de validação. Exceções de negócio
(BionException) viram resposta de erro; qualquer outra exceção não é tratada
aqui e segue para o tratamento global de erros da aplicação.
"""

from functools import wraps

from flask import Blueprint, request
from src.core.responses import json_success, json_error
from src.core.exceptions import BionException, DadosInvalidosError
from .service import EstatisticasService
from src.core.session import requer_admin, requer_login, get_id_empresa_sessao


bp = Blueprint("estatisticas", __name__)
_svc = EstatisticasService()


# Faixas aceitas para os parâmetros numéricos da query string.
_DIAS_MIN, _DIAS_MAX = 1, 365
_LIMITE_MIN, _LIMITE_MAX = 1, 50


def _responder_erros(rota):
    """Converte BionException da rota em json_error; outras exceções não são tratadas aqui."""
    @wraps(rota)
    def interna(*args, **kwargs):
        try:
            return rota(*args, **kwargs)
        except BionException as ex:
            return json_error(ex.message, ex.status_code)
    return interna


def _arg_int(nome: str, padrao: int, minimo: int, maximo: int) -> int:
    """Lê um inteiro da query string.

    Ausente ou não numérico devolve o padrão; fora de [minimo, maximo] levanta
    DadosInvalidosError.
    """
    valor = request.args.get(nome, default=padrao, type=int)
    if not minimo <= valor <= maximo:
        raise DadosInvalidosError(f"'{nome}' deve estar entre {minimo} e {maximo}.", campo=nome)
    return valor


def _dias(padrao: int) -> int:
    return _arg_int("dias", padrao, _DIAS_MIN, _DIAS_MAX)


def _limite(padrao: int, nome: str = "limite") -> int:
    return _arg_int(nome, padrao, _LIMITE_MIN, _LIMITE_MAX)


class EstatisticasController:

    # ============================================================
    # ADMIN — Gerenciamento operacional (volume, tempo, equipe)
    # ============================================================

    @staticmethod
    @bp.get("/geral")
    @requer_admin
    @_responder_erros
    def estatisticas_geral():
        """Resumo geral: profissionais (total, ativos, pendentes), consultas de hoje e pacientes cadastrados."""
        return json_success(data=_svc.estatisticas_geral(get_id_empresa_sessao()))

    @staticmethod
    @bp.get("/atendimentos/volume")
    @requer_admin
    @_responder_erros
    def volume_atendimentos():
        """A1: volume de atendimentos por dia. Query: dias (padrão 30)."""
        dados = _svc.volume_atendimentos(get_id_empresa_sessao(), dias=_dias(30))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/atendimentos/tempo-medio")
    @requer_admin
    @_responder_erros
    def tempo_medio_atendimento():
        """A2: tempo médio de atendimento por tipo. Query: dias (padrão 30)."""
        dados = _svc.tempo_medio_atendimento(get_id_empresa_sessao(), dias=_dias(30))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/atendimentos/taxa-conclusao")
    @requer_admin
    @_responder_erros
    def taxa_conclusao():
        """A3: taxa de conclusão vs. abandono. Query: dias (padrão 30)."""
        dados = _svc.taxa_conclusao(get_id_empresa_sessao(), dias=_dias(30))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/equipe/efetivo")
    @requer_admin
    @_responder_erros
    def efetivo_ativo():
        """A4: efetivo ativo por papel."""
        return json_success(data=_svc.efetivo_ativo(get_id_empresa_sessao()))

    @staticmethod
    @bp.get("/equipe/engajamento")
    @requer_admin
    @_responder_erros
    def engajamento_equipe():
        """A5: engajamento/atividade da equipe. Query: dias (padrão 7)."""
        dados = _svc.engajamento_equipe(get_id_empresa_sessao(), dias=_dias(7))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/atendimentos/tendencia-eficiencia")
    @requer_admin
    @_responder_erros
    def tendencia_eficiencia():
        """E2: tendência de eficiência acumulada. Query: dias (padrão 30)."""
        dados = _svc.tendencia_eficiencia(get_id_empresa_sessao(), dias=_dias(30))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/pacientes/tipo-sanguineo")
    @requer_admin
    @_responder_erros
    def distribuicao_tipo_sanguineo():
        """F3: distribuição de tipo sanguíneo na base de pacientes."""
        return json_success(data=_svc.distribuicao_tipo_sanguineo(get_id_empresa_sessao()))

    # ============================================================
    # ADMIN + MÉDICO — Qualidade e confiabilidade da IA
    # ============================================================

    @staticmethod
    @bp.get("/ia/confianca-media")
    @requer_login
    @_responder_erros
    def confianca_media_ia():
        """B1: confiança média da IA. Query: dias (padrão 30)."""
        dados = _svc.confianca_media_ia(get_id_empresa_sessao(), dias=_dias(30))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/ia/completude-media")
    @requer_login
    @_responder_erros
    def completude_media_ia():
        """B2: completude média dos dados de entrada. Query: dias (padrão 30)."""
        dados = _svc.completude_media_ia(get_id_empresa_sessao(), dias=_dias(30))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/ia/versoes-em-uso")
    @requer_admin
    @_responder_erros
    def versoes_ia_em_uso():
        """B4: versões do modelo de IA em uso. Query: dias (padrão 30)."""
        dados = _svc.versoes_ia_em_uso(get_id_empresa_sessao(), dias=_dias(30))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/ia/correlacao-completude-confianca")
    @requer_admin
    @_responder_erros
    def correlacao_completude_confianca():
        """E3: correlação entre completude dos dados e confiança da IA. Query: dias (padrão 30)."""
        dados = _svc.correlacao_completude_confianca(get_id_empresa_sessao(), dias=_dias(30))
        return json_success(data=dados)

    # ============================================================
    # MÉDICO / ENFERMEIRO — Epidemiológico (pesquisa e vigilância)
    # ============================================================

    @staticmethod
    @bp.get("/epidemiologico/top-cid-regiao")
    @requer_login
    @_responder_erros
    def top_cid_por_regiao():
        """C1: doenças (CID) mais comuns por região. Query: dias (padrão 14), limite (padrão 10)."""
        dados = _svc.top_cid_por_regiao(
            get_id_empresa_sessao(), dias=_dias(14), limite=_limite(10)
        )
        return json_success(data=dados)

    @staticmethod
    @bp.get("/epidemiologico/evolucao-cid/<string:codigo_cid10>")
    @requer_login
    @_responder_erros
    def evolucao_cid(codigo_cid10):
        """C2: evolução temporal de um CID específico. Query: dias (padrão 30)."""
        dados = _svc.evolucao_cid(
            get_id_empresa_sessao(), codigo_cid10=codigo_cid10, dias=_dias(30)
        )
        return json_success(data=dados)

    @staticmethod
    @bp.get("/epidemiologico/incidencia-regiao")
    @requer_login
    @_responder_erros
    def incidencia_por_regiao():
        """C3: incidência por 100 mil habitantes, por região. Query: dias (padrão 14)."""
        dados = _svc.incidencia_por_regiao(get_id_empresa_sessao(), dias=_dias(14))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/epidemiologico/tempo-ate-atendimento")
    @requer_login
    @_responder_erros
    def tempo_ate_atendimento():
        """C4: tempo até a busca por atendimento (sintoma -> consulta). Query: dias (padrão 30)."""
        dados = _svc.tempo_ate_atendimento(get_id_empresa_sessao(), dias=_dias(30))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/epidemiologico/queixas-frequentes")
    @requer_login
    @_responder_erros
    def queixas_mais_frequentes():
        """C5: queixas principais mais frequentes. Query: dias (padrão 30), top (padrão 15)."""
        dados = _svc.queixas_mais_frequentes(
            get_id_empresa_sessao(), dias=_dias(30), top=_limite(15, "top")
        )
        return json_success(data=dados)

    # ============================================================
    # MÉDICO — Farmacovigilância e segurança do paciente
    # ============================================================

    @staticmethod
    @bp.get("/medicamentos/interacoes-gravidade")
    @requer_login
    @_responder_erros
    def interacoes_por_gravidade():
        """D1: interações medicamentosas cadastradas, por gravidade (dado global, não filtra por empresa)."""
        return json_success(data=_svc.interacoes_por_gravidade())

    @staticmethod
    @bp.get("/alergias/top-substancias")
    @requer_login
    @_responder_erros
    def alergias_top_substancias():
        """D2: alergias mais reportadas, por substância. Query: limite (padrão 10)."""
        dados = _svc.alergias_top_substancias(get_id_empresa_sessao(), limite=_limite(10))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/alergias/<string:substancia>/gravidade")
    @requer_login
    @_responder_erros
    def alergia_gravidade_por_substancia(substancia):
        """D2 (detalhe): gravidade das reações a uma substância."""
        dados = _svc.alergia_gravidade_por_substancia(get_id_empresa_sessao(), substancia=substancia)
        return json_success(data=dados)

    @staticmethod
    @bp.get("/alergias/gravidade-geral")
    @requer_login
    @_responder_erros
    def alergias_gravidade_geral():
        """F4: gravidade geral das reações alérgicas (sem filtro por substância)."""
        return json_success(data=_svc.alergias_gravidade_geral(get_id_empresa_sessao()))

    @staticmethod
    @bp.get("/exames/urgencia-por-origem")
    @requer_login
    @_responder_erros
    def urgencia_exames_por_origem():
        """D3: urgência de exames, IA vs. profissional. Query: dias (padrão 30)."""
        dados = _svc.urgencia_exames_por_origem(get_id_empresa_sessao(), dias=_dias(30))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/medicamentos/top-por-classe")
    @requer_login
    @_responder_erros
    def medicamentos_top_por_classe():
        """D4: medicamentos mais prescritos por classe. Query: dias (padrão 30), limite (padrão 10)."""
        dados = _svc.medicamentos_top_por_classe(
            get_id_empresa_sessao(), dias=_dias(30), limite=_limite(10)
        )
        return json_success(data=dados)

    @staticmethod
    @bp.get("/medicamentos/top-por-classe/<string:classe>")
    @requer_login
    @_responder_erros
    def medicamentos_top_principios_por_classe(classe):
        """D4 (detalhe): princípios ativos mais prescritos dentro de uma classe. Query: dias (padrão 30), limite (padrão 10)."""
        dados = _svc.medicamentos_top_principios_por_classe(
            get_id_empresa_sessao(), classe=classe, dias=_dias(30), limite=_limite(10)
        )
        return json_success(data=dados)

    # ============================================================
    # MÉDICO — Histórico clínico da base de pacientes
    # ============================================================

    @staticmethod
    @bp.get("/pacientes/doencas-cronicas-top")
    @requer_login
    @_responder_erros
    def doencas_cronicas_top():
        """F1: doenças crônicas mais comuns na base. Query: limite (padrão 10)."""
        dados = _svc.doencas_cronicas_top(get_id_empresa_sessao(), limite=_limite(10))
        return json_success(data=dados)

    @staticmethod
    @bp.get("/pacientes/uso-continuo-medicacao")
    @requer_login
    @_responder_erros
    def uso_continuo_medicacao():
        """F2: percentual de pacientes em uso contínuo de medicação."""
        return json_success(data=_svc.uso_continuo_medicacao(get_id_empresa_sessao()))