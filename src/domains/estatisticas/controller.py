from flask import Blueprint, request, session
from src.core.responses import json_success, json_error
from .services.service import EstatisticasService
from src.core.session import requer_papel, get_id_empresa_sessao


bp = Blueprint("estatisticas", __name__)
_svc = EstatisticasService()


# ============================================================
# ADMIN — Gerenciamento operacional (volume, tempo, equipe)
# ============================================================

@bp.get("/geral")
@requer_papel("admin")
def estatisticas_geral():
    try:
        dados = _svc.estatisticas_geral(get_id_empresa_sessao())
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))

# --- A1: Volume de atendimentos ---
@bp.get("/atendimentos/volume")
@requer_papel("admin")
def volume_atendimentos():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.volume_atendimentos(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- A2: Tempo médio de atendimento ---
@bp.get("/atendimentos/tempo-medio")
@requer_papel("admin")
def tempo_medio_atendimento():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.tempo_medio_atendimento(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- A3: Taxa de conclusão vs. abandono ---
@bp.get("/atendimentos/taxa-conclusao")
@requer_papel("admin")
def taxa_conclusao():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.taxa_conclusao(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- A4: Efetivo ativo por papel ---
@bp.get("/equipe/efetivo")
@requer_papel("admin")
def efetivo_ativo():
    try:
        dados = _svc.efetivo_ativo(get_id_empresa_sessao())
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- A5: Engajamento/atividade da equipe ---
@bp.get("/equipe/engajamento")
@requer_papel("admin")
def engajamento_equipe():
    try:
        dias = request.args.get("dias", default=7, type=int)
        dados = _svc.engajamento_equipe(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- E2: Tendência de eficiência acumulada ---
@bp.get("/atendimentos/tendencia-eficiencia")
@requer_papel("admin")
def tendencia_eficiencia():
    try:
        dias = request.args.get("dias", default=60, type=int)
        dados = _svc.tendencia_eficiencia(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- F3: Distribuição de tipo sanguíneo na base ---
@bp.get("/pacientes/tipo-sanguineo")
@requer_papel("admin")
def distribuicao_tipo_sanguineo():
    try:
        dados = _svc.distribuicao_tipo_sanguineo(get_id_empresa_sessao())
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# ============================================================
# ADMIN + MÉDICO — Qualidade e confiabilidade da IA
# ============================================================

# --- B1: Confiança média da IA ---
@bp.get("/ia/confianca-media")
@requer_papel("admin")
def confianca_media_ia():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.confianca_media_ia(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- B2: Completude média dos dados de entrada ---
@bp.get("/ia/completude-media")
@requer_papel("admin")
def completude_media_ia():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.completude_media_ia(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- B4: Versão do modelo de IA em uso ---
@bp.get("/ia/versoes-em-uso")
@requer_papel("admin")
def versoes_ia_em_uso():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.versoes_ia_em_uso(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- E3: Correlação completude x confiança ---
@bp.get("/ia/correlacao-completude-confianca")
@requer_papel("admin")
def correlacao_completude_confianca():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.correlacao_completude_confianca(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# ============================================================
# MÉDICO / ENFERMEIRO — Epidemiológico (pesquisa e vigilância)
# ============================================================

# --- C1: Doenças mais comuns por região ---
@bp.get("/epidemiologico/top-cid-regiao")
@requer_papel("admin")
def top_cid_por_regiao():
    try:
        dias = request.args.get("dias", default=14, type=int)
        limite = request.args.get("limite", default=10, type=int)
        dados = _svc.top_cid_por_regiao(get_id_empresa_sessao(), dias=dias, limite=limite)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- C2: Evolução temporal de um CID específico ---
@bp.get("/epidemiologico/evolucao-cid/<string:codigo_cid10>")
@requer_papel("admin")
def evolucao_cid(codigo_cid10):
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.evolucao_cid(get_id_empresa_sessao(), codigo_cid10=codigo_cid10, dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- C3: Incidência por 100 mil habitantes ---
@bp.get("/epidemiologico/incidencia-regiao")
@requer_papel("admin")
def incidencia_por_regiao():
    try:
        dias = request.args.get("dias", default=14, type=int)
        dados = _svc.incidencia_por_regiao(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- C4: Tempo até busca por atendimento (sintoma -> consulta) ---
@bp.get("/epidemiologico/tempo-ate-atendimento")
@requer_papel("admin")
def tempo_ate_atendimento():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.tempo_ate_atendimento(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- C5: Queixas principais mais frequentes ---
@bp.get("/epidemiologico/queixas-frequentes")
@requer_papel("admin")
def queixas_mais_frequentes():
    try:
        dias = request.args.get("dias", default=30, type=int)
        top = request.args.get("top", default=15, type=int)
        dados = _svc.queixas_mais_frequentes(get_id_empresa_sessao(), dias=dias, top=top)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# ============================================================
# MÉDICO — Farmacovigilância e segurança do paciente
# ============================================================

# --- D1: Interações medicamentosas cadastradas por gravidade ---
@bp.get("/medicamentos/interacoes-gravidade")
@requer_papel("admin")
def interacoes_por_gravidade():
    try:
        dados = _svc.interacoes_por_gravidade()
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- D2: Alergias mais reportadas (por substância) ---
@bp.get("/alergias/top-substancias")
@requer_papel("admin")
def alergias_top_substancias():
    try:
        limite = request.args.get("limite", default=10, type=int)
        dados = _svc.alergias_top_substancias(get_id_empresa_sessao(), limite=limite)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- D2 (detalhe): gravidade por substância ---
@bp.get("/alergias/<string:substancia>/gravidade")
@requer_papel("admin")
def alergia_gravidade_por_substancia(substancia):
    try:
        dados = _svc.alergia_gravidade_por_substancia(get_id_empresa_sessao(), substancia=substancia)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- F4: Gravidade geral das reações alérgicas (sem filtro por substância) ---
@bp.get("/alergias/gravidade-geral")
@requer_papel("admin")
def alergias_gravidade_geral():
    try:
        dados = _svc.alergias_gravidade_geral(get_id_empresa_sessao())
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- D3: Urgência de exames -- IA vs. profissional ---
@bp.get("/exames/urgencia-por-origem")
@requer_papel("admin")
def urgencia_exames_por_origem():
    try:
        dias = request.args.get("dias", default=30, type=int)
        dados = _svc.urgencia_exames_por_origem(get_id_empresa_sessao(), dias=dias)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- D4: Medicamentos mais prescritos por classe ---
@bp.get("/medicamentos/top-por-classe")
@requer_papel("admin")
def medicamentos_top_por_classe():
    try:
        dias = request.args.get("dias", default=30, type=int)
        limite = request.args.get("limite", default=10, type=int)
        dados = _svc.medicamentos_top_por_classe(get_id_empresa_sessao(), dias=dias, limite=limite)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- D4 (detalhe): princípios ativos dentro de 1 classe ---
@bp.get("/medicamentos/top-por-classe/<string:classe>")
@requer_papel("admin")
def medicamentos_top_principios_por_classe(classe):
    try:
        dias = request.args.get("dias", default=30, type=int)
        limite = request.args.get("limite", default=10, type=int)
        dados = _svc.medicamentos_top_principios_por_classe(
            get_id_empresa_sessao(), classe=classe, dias=dias, limite=limite
        )
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# ============================================================
# MÉDICO — Histórico clínico da base de pacientes
# ============================================================

# --- F1: Doenças crônicas mais comuns na base ---
@bp.get("/pacientes/doencas-cronicas-top")
@requer_papel("admin")
def doencas_cronicas_top():
    try:
        limite = request.args.get("limite", default=10, type=int)
        dados = _svc.doencas_cronicas_top(get_id_empresa_sessao(), limite=limite)
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))


# --- F2: Pacientes em uso contínuo de medicação (%) ---
@bp.get("/pacientes/uso-continuo-medicacao")
@requer_papel("admin")
def uso_continuo_medicacao():
    try:
        dados = _svc.uso_continuo_medicacao(get_id_empresa_sessao())
        return json_success(dados)
    except Exception as e:
        return json_error(str(e))