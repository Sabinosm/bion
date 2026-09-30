"""Seed: modulos 1 a 4 (classificadores e pontuadores mais comuns).

Cada entrada tem: sigla, nome, tipo_modulo (tag de dominio), a versao
1.0 (configuracao_json + explicacao_json), e os campos que a versao usa
(codigo_variavel, obrigatorio).

Todas as faixas seguem a convencao [min, max) fixada no config_schemas.py
do passo 2: minimo inclusivo, maximo exclusivo.
"""

MODULO_IMC = dict(
    sigla="IMC",
    nome_modulo="Índice de Massa Corporal",
    tipo_modulo="epidemiologico",
    familia_calculo="classificador",
    tipo_saida="categoria",
    referencia_bibliografica="World Health Organization. Obesity: preventing and managing the global epidemic. WHO, 2000.",
    versao="1.0",
    campos=[("imc", True)],
    configuracao_json={
        "familia": "classificador", "modo": "faixas", "variavel": "imc",
        "categorias": [
            {"min": None, "max": 18.5, "classificacao": "baixo_peso", "gravidade": 1},
            {"min": 18.5, "max": 25, "classificacao": "eutrofico", "gravidade": 0},
            {"min": 25, "max": 30, "classificacao": "sobrepeso", "gravidade": 1},
            {"min": 30, "max": 35, "classificacao": "obesidade_grau_1", "gravidade": 2},
            {"min": 35, "max": 40, "classificacao": "obesidade_grau_2", "gravidade": 3},
            {"min": 40, "max": None, "classificacao": "obesidade_grau_3", "gravidade": 4},
        ],
    },
    explicacao_json={
        "o_que_e": "Classifica o estado nutricional a partir da relação entre peso e altura ao quadrado (kg/m²).",
        "quando_usar": "Rastreio nutricional de rotina em qualquer consulta de avaliação médica.",
        "como_interpretar": "< 18,5 baixo peso; 18,5–25 eutrófico; 25–30 sobrepeso; 30–35 obesidade grau I; 35–40 grau II; ≥ 40 grau III.",
        "limitacoes": "Não distingue massa magra de massa gorda; pode classificar atletas como sobrepeso/obesidade. Faixas de corte diferem em populações pediátricas e não se aplicam aqui.",
    },
)

MODULO_PA = dict(
    sigla="PA",
    nome_modulo="Classificação da Pressão Arterial",
    tipo_modulo="epidemiologico",
    familia_calculo="classificador",
    tipo_saida="categoria",
    referencia_bibliografica="Diretriz Brasileira de Hipertensão Arterial — 2020 (Sociedade Brasileira de Cardiologia).",
    versao="1.0",
    campos=[("pa_sistolica", True), ("pa_diastolica", True)],
    configuracao_json={
        "familia": "classificador", "modo": "regras",
        "regras": [
            {"se": {"ou": [
                {"variavel": "pa_sistolica", "op": ">=", "valor": 180},
                {"variavel": "pa_diastolica", "op": ">=", "valor": 110},
            ]}, "classificacao": "hipertensao_estagio_3", "gravidade": 4},
            {"se": {"ou": [
                {"variavel": "pa_sistolica", "op": ">=", "valor": 160},
                {"variavel": "pa_diastolica", "op": ">=", "valor": 100},
            ]}, "classificacao": "hipertensao_estagio_2", "gravidade": 3},
            {"se": {"ou": [
                {"variavel": "pa_sistolica", "op": ">=", "valor": 140},
                {"variavel": "pa_diastolica", "op": ">=", "valor": 90},
            ]}, "classificacao": "hipertensao_estagio_1", "gravidade": 2},
            {"se": {"ou": [
                {"variavel": "pa_sistolica", "op": ">=", "valor": 130},
                {"variavel": "pa_diastolica", "op": ">=", "valor": 85},
            ]}, "classificacao": "limitrofe", "gravidade": 1},
        ],
        "padrao": {"classificacao": "otima", "gravidade": 0},
    },
    explicacao_json={
        "o_que_e": "Classifica o nível pressórico a partir da pressão sistólica e diastólica.",
        "quando_usar": "Rastreio de rotina e acompanhamento de pacientes hipertensos ou em risco.",
        "como_interpretar": "A classificação usa o pior dos dois valores (sistólica ou diastólica). Estágios: ótima < 130/85, limítrofe, estágio 1 (≥140/90), estágio 2 (≥160/100), estágio 3 (≥180/110).",
        "limitacoes": "Uma única aferição não confirma diagnóstico de hipertensão; exige medidas repetidas ou MAPA/MRPA conforme diretriz.",
    },
)

MODULO_PHQ9 = dict(
    sigla="PHQ9",
    nome_modulo="PHQ-9 — Rastreio de Depressão",
    tipo_modulo="epidemiologico",
    familia_calculo="pontuador",
    tipo_saida="pontos",
    referencia_bibliografica="Kroenke K, Spitzer RL, Williams JB. The PHQ-9: validity of a brief depression severity measure. J Gen Intern Med. 2001;16(9):606-13.",
    versao="1.0",
    campos=[(f"phq9_item{n}", True) for n in range(1, 10)],
    configuracao_json={
        "familia": "pontuador",
        "parametros": [
            {"variavel": f"phq9_item{n}", "tipo": "mapeamento", "mapa": {"0": 0, "1": 1, "2": 2, "3": 3}}
            for n in range(1, 10)
        ],
        "interpretacao": {
            "faixas": [
                {"min": None, "max": 5, "classificacao": "minima", "gravidade": 0},
                {"min": 5, "max": 10, "classificacao": "leve", "gravidade": 1},
                {"min": 10, "max": 15, "classificacao": "moderada", "gravidade": 2},
                {"min": 15, "max": 20, "classificacao": "moderadamente_grave", "gravidade": 3},
                {"min": 20, "max": None, "classificacao": "grave", "gravidade": 4},
            ]
        },
    },
    explicacao_json={
        "o_que_e": "Questionário de 9 itens para rastreio e gravidade de sintomas depressivos nas últimas 2 semanas.",
        "quando_usar": "Rastreio de rotina na atenção primária e acompanhamento de resposta ao tratamento.",
        "como_interpretar": "Soma de 0 a 27: 0–4 mínima, 5–9 leve, 10–14 moderada, 15–19 moderadamente grave, 20–27 grave.",
        "limitacoes": "É um instrumento de rastreio, não substitui avaliação clínica ou diagnóstico. O item 9 (ideação de morte/autolesão) exige atenção clínica direta sempre que pontuado, independente do total.",
    },
)

MODULO_GAD7 = dict(
    sigla="GAD7",
    nome_modulo="GAD-7 — Rastreio de Ansiedade",
    tipo_modulo="epidemiologico",
    familia_calculo="pontuador",
    tipo_saida="pontos",
    referencia_bibliografica="Spitzer RL, Kroenke K, Williams JB, Löwe B. A brief measure for assessing generalized anxiety disorder: the GAD-7. Arch Intern Med. 2006;166(10):1092-7.",
    versao="1.0",
    campos=[(f"gad7_item{n}", True) for n in range(1, 8)],
    configuracao_json={
        "familia": "pontuador",
        "parametros": [
            {"variavel": f"gad7_item{n}", "tipo": "mapeamento", "mapa": {"0": 0, "1": 1, "2": 2, "3": 3}}
            for n in range(1, 8)
        ],
        "interpretacao": {
            "faixas": [
                {"min": None, "max": 5, "classificacao": "minima", "gravidade": 0},
                {"min": 5, "max": 10, "classificacao": "leve", "gravidade": 1},
                {"min": 10, "max": 15, "classificacao": "moderada", "gravidade": 2},
                {"min": 15, "max": None, "classificacao": "grave", "gravidade": 3},
            ]
        },
    },
    explicacao_json={
        "o_que_e": "Questionário de 7 itens para rastreio e gravidade de sintomas de ansiedade generalizada nas últimas 2 semanas.",
        "quando_usar": "Rastreio de rotina na atenção primária, especialmente junto ao PHQ-9 (comorbidade ansiedade-depressão é frequente).",
        "como_interpretar": "Soma de 0 a 21: 0–4 mínima, 5–9 leve, 10–14 moderada, 15–21 grave. Corte ≥10 é o ponto recomendado para investigação adicional de transtorno de ansiedade generalizada.",
        "limitacoes": "É rastreio, não diagnóstico. Não diferencia TAG de outros transtornos de ansiedade (pânico, fobia social, TEPT) — todos podem elevar o escore.",
    },
)
