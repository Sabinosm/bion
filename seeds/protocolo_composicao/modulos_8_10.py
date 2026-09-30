"""Seed: modulos 8 a 10.

MODULO_RISCO_CV: risco cardiovascular. NAO reproduz Framingham (formula
logistica com coeficientes por sexo/idade que exigiria validacao
estatistica externa para reproduzir com fidelidade) -- em vez disso,
modela uma contagem de fatores de risco maiores, abordagem tambem descrita
na literatura como rastreio inicial simplificado. Isso e uma SIMPLIFICACAO
DELIBERADA, documentada na explicacao do modulo para nao ser confundida
com o escore de Framingham propriamente dito.

MODULO_WELLS_TEP: usa a versao de 7 criterios objetivos do escore de
Wells para TEP, com o modelo de tres niveis (baixo/moderado/alto), citado
nas fontes de wikem.org e sanarmed.com. Pesos fracionarios (1.5, 3.0) sao
suportados pelo pontuador porque 'pontos' aceita qualquer numero.

MODULO_ELEGIBILIDADE_ADULTO: modulo GATILHO de exemplo (idade >= 18),
para demonstrar o mecanismo de regra_gatilho_json em protocolo_composicao_config.
"""

MODULO_RISCO_CV = dict(
    sigla="RISCO_CV_SIMPLIFICADO",
    nome_modulo="Contagem de Fatores de Risco Cardiovascular",
    tipo_modulo="epidemiologico",
    familia_calculo="pontuador",
    tipo_saida="pontos",
    referencia_bibliografica=(
        "Simplificação deliberada: NÃO é o escore de Framingham (que exige "
        "coeficientes logísticos por sexo/idade não reproduzidos aqui). "
        "Conta fatores de risco maiores classicamente descritos (tabagismo, "
        "diabetes, dislipidemia, hipertensão, idade)."
    ),
    versao="1.0",
    campos=[
        ("fumante_atual", True), ("diabetes_diagnosticado", True),
        ("dislipidemia_diagnosticada", True), ("idade", True),
    ],
    configuracao_json={
        "familia": "pontuador",
        "parametros": [
            {"variavel": "fumante_atual", "tipo": "mapeamento", "mapa": {"True": 1, "False": 0}},
            {"variavel": "diabetes_diagnosticado", "tipo": "mapeamento", "mapa": {"True": 1, "False": 0}},
            {"variavel": "dislipidemia_diagnosticada", "tipo": "mapeamento", "mapa": {"True": 1, "False": 0}},
            {"variavel": "idade", "tipo": "faixas", "faixas": [
                {"min": None, "max": 45, "pontos": 0},
                {"min": 45, "max": None, "pontos": 1},
            ]},
        ],
        "interpretacao": {
            "faixas": [
                {"min": None, "max": 1, "classificacao": "baixo_risco", "gravidade": 0},
                {"min": 1, "max": 3, "classificacao": "risco_moderado", "gravidade": 1},
                {"min": 3, "max": None, "classificacao": "risco_elevado", "gravidade": 2},
            ]
        },
    },
    explicacao_json={
        "o_que_e": "Contagem simplificada de fatores de risco cardiovascular maiores (tabagismo, diabetes, dislipidemia, idade ≥45).",
        "quando_usar": "Triagem inicial de risco cardiovascular em consulta de rotina, quando um escore validado (Framingham, ASCVD) ainda não está disponível.",
        "como_interpretar": "0-1 fator: baixo risco. 2 fatores: risco moderado. 3+ fatores: risco elevado.",
        "limitacoes": "NÃO é o escore de Framingham nem substitui uma calculadora de risco validada — é uma contagem de fatores, não uma probabilidade estimada em anos. Use como triagem inicial; encaminhe para cálculo de risco formal quando indicado.",
    },
)

MODULO_WELLS_TEP = dict(
    sigla="WELLS_TEP",
    nome_modulo="Escore de Wells para TEP",
    tipo_modulo="epidemiologico",
    familia_calculo="pontuador",
    tipo_saida="pontos",
    referencia_bibliografica="Wells PS, et al. Derivation of a simple clinical model to categorize patients probability of pulmonary embolism. Thromb Haemost. 2000;83(3):416-20.",
    versao="1.0",
    campos=[
        ("sinais_tvp", True), ("tep_diagnostico_mais_provavel", True),
        ("frequencia_cardiaca", True), ("imobilizacao_ou_cirurgia_recente", True),
        ("tvp_ou_tep_previo", True), ("hemoptise", True), ("malignidade_ativa", True),
    ],
    configuracao_json={
        "familia": "pontuador",
        "parametros": [
            {"variavel": "sinais_tvp", "tipo": "mapeamento", "mapa": {"True": 3, "False": 0}},
            {"variavel": "tep_diagnostico_mais_provavel", "tipo": "mapeamento", "mapa": {"True": 3, "False": 0}},
            {"variavel": "frequencia_cardiaca", "tipo": "faixas", "faixas": [
                {"min": None, "max": 100, "pontos": 0},
                {"min": 100, "max": None, "pontos": 1.5},
            ]},
            {"variavel": "imobilizacao_ou_cirurgia_recente", "tipo": "mapeamento", "mapa": {"True": 1.5, "False": 0}},
            {"variavel": "tvp_ou_tep_previo", "tipo": "mapeamento", "mapa": {"True": 1.5, "False": 0}},
            {"variavel": "hemoptise", "tipo": "mapeamento", "mapa": {"True": 1, "False": 0}},
            {"variavel": "malignidade_ativa", "tipo": "mapeamento", "mapa": {"True": 1, "False": 0}},
        ],
        "interpretacao": {
            "faixas": [
                {"min": None, "max": 2, "classificacao": "baixa_probabilidade", "gravidade": 0},
                {"min": 2, "max": 6, "classificacao": "probabilidade_moderada", "gravidade": 1},
                {"min": 6, "max": None, "classificacao": "alta_probabilidade", "gravidade": 2},
            ]
        },
    },
    explicacao_json={
        "o_que_e": "Estima a probabilidade clínica pré-teste de tromboembolismo pulmonar (TEP) a partir de 7 critérios clínicos objetivos.",
        "quando_usar": "Suspeita clínica de TEP, antes de solicitar D-dímero ou angiotomografia.",
        "como_interpretar": "Modelo de três níveis: 0–1 baixa probabilidade (considerar D-dímero), 2–6 probabilidade moderada, >6 alta probabilidade (considerar exame de imagem direto).",
        "limitacoes": "O critério 'TEP é o diagnóstico mais provável' é subjetivo e pode variar entre avaliadores. O escore não deve ser usado isoladamente — sempre em conjunto com julgamento clínico e a regra PERC quando aplicável.",
    },
)

MODULO_ELEGIBILIDADE_ADULTO = dict(
    sigla="ELEGIBILIDADE_ADULTO",
    nome_modulo="Elegibilidade — Paciente Adulto",
    tipo_modulo="institucional",
    familia_calculo="regra",
    tipo_saida="flag",
    referencia_bibliografica="Critério administrativo interno (não corresponde a instrumento clínico publicado).",
    versao="1.0",
    campos=[("idade", True)],
    configuracao_json={
        "familia": "regra",
        "condicao": {"variavel": "idade", "op": ">=", "valor": 18},
        "saida_verdadeiro": {"classificacao": "elegivel"},
        "saida_falso": {"classificacao": "nao_elegivel", "motivo": "Paciente menor de 18 anos"},
    },
    explicacao_json={
        "o_que_e": "Módulo de elegibilidade etária, usado como gatilho para desligar módulos validados apenas para a população adulta.",
        "quando_usar": "Sempre que um protocolo composto combinar módulos cuja validação se restringe a adultos.",
        "como_interpretar": "Resultado é 'elegível' ou 'não_elegível'. Não gera pontuação nem alerta clínico isolado — serve para controlar quais outros módulos do protocolo são executados.",
        "limitacoes": "É um critério administrativo, não clínico; não deve ser interpretado como avaliação de maturidade ou capacidade civil.",
    },
)
