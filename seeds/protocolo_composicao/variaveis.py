"""Seed: dicionario de variaveis clinicas compartilhadas pelos 10 modulos.

Cada entrada e o que criara uma linha em variavel_clinica. `codigo` e a
chave estavel usada dentro dos configuracao_json dos modulos -- nunca o
id numerico.

valor_min/valor_max sao limites de PLAUSIBILIDADE (o que o backend aceita
como entrada), nao limites clinicos de normalidade -- por isso idade vai
ate 130, nao ate uma faixa "saudavel".
"""

VARIAVEIS = [
    # ---- antropometria ----
    dict(codigo="peso_kg", nome="Peso", tipo_dado="numerico", unidade="kg", valor_min=1, valor_max=400),
    dict(codigo="altura_m", nome="Altura", tipo_dado="numerico", unidade="m", valor_min=0.3, valor_max=2.5),
    dict(codigo="imc", nome="IMC", tipo_dado="numerico", unidade="kg/m2", valor_min=5, valor_max=100),

    # ---- sinais vitais / demografia ----
    dict(codigo="idade", nome="Idade", tipo_dado="numerico", unidade="anos", valor_min=0, valor_max=130),
    dict(codigo="sexo_biologico", nome="Sexo biológico", tipo_dado="categorico",
         opcoes=[{"valor": "masculino", "rotulo": "Masculino"}, {"valor": "feminino", "rotulo": "Feminino"}]),
    dict(codigo="pa_sistolica", nome="Pressão arterial sistólica", tipo_dado="numerico", unidade="mmHg", valor_min=40, valor_max=300),
    dict(codigo="pa_diastolica", nome="Pressão arterial diastólica", tipo_dado="numerico", unidade="mmHg", valor_min=20, valor_max=200),
    dict(codigo="frequencia_cardiaca", nome="Frequência cardíaca", tipo_dado="numerico", unidade="bpm", valor_min=20, valor_max=250),

    # ---- comorbidades / medicação ----
    dict(codigo="numero_medicamentos", nome="Número de medicamentos em uso contínuo", tipo_dado="numerico", valor_min=0, valor_max=50),

    # ---- PHQ-9 (9 itens, cada um 0-3) ----
    *[
        dict(codigo=f"phq9_item{n}", nome=f"PHQ-9 — item {n}", tipo_dado="categorico",
             opcoes=[
                 {"valor": "0", "rotulo": "Nunca"},
                 {"valor": "1", "rotulo": "Vários dias"},
                 {"valor": "2", "rotulo": "Mais da metade dos dias"},
                 {"valor": "3", "rotulo": "Quase todos os dias"},
             ])
        for n in range(1, 10)
    ],

    # ---- GAD-7 (7 itens, cada um 0-3) ----
    *[
        dict(codigo=f"gad7_item{n}", nome=f"GAD-7 — item {n}", tipo_dado="categorico",
             opcoes=[
                 {"valor": "0", "rotulo": "Nunca"},
                 {"valor": "1", "rotulo": "Vários dias"},
                 {"valor": "2", "rotulo": "Mais da metade dos dias"},
                 {"valor": "3", "rotulo": "Quase todos os dias"},
             ])
        for n in range(1, 8)
    ],

    # ---- AUDIT-C (3 itens, escalas variam por item) ----
    dict(codigo="auditc_item1", nome="AUDIT-C — frequência de consumo", tipo_dado="categorico",
         opcoes=[{"valor": str(i), "rotulo": r} for i, r in enumerate([
             "Nunca", "Mensalmente ou menos", "2-4 vezes ao mês", "2-3 vezes por semana", "4+ vezes por semana",
         ])]),
    dict(codigo="auditc_item2", nome="AUDIT-C — doses em um dia típico", tipo_dado="categorico",
         opcoes=[{"valor": str(i), "rotulo": r} for i, r in enumerate([
             "1 ou 2", "3 ou 4", "5 ou 6", "7 a 9", "10 ou mais",
         ])]),
    dict(codigo="auditc_item3", nome="AUDIT-C — frequência de ≥6 doses numa ocasião", tipo_dado="categorico",
         opcoes=[{"valor": str(i), "rotulo": r} for i, r in enumerate([
             "Nunca", "Menos que mensalmente", "Mensalmente", "Semanalmente", "Diariamente ou quase",
         ])]),

    # ---- risco de queda (fatores objetivos) ----
    dict(codigo="queda_ultimo_ano", nome="Caiu ao menos uma vez no último ano", tipo_dado="booleano"),
    dict(codigo="marcha_alterada", nome="Marcha ou equilíbrio alterados (avaliação clínica)", tipo_dado="booleano"),

    # ---- risco cardiovascular / TEV (simplificados por regra, sem escore proprietário) ----
    dict(codigo="fumante_atual", nome="Fumante atual", tipo_dado="booleano"),
    dict(codigo="diabetes_diagnosticado", nome="Diabetes diagnosticado", tipo_dado="booleano"),
    dict(codigo="dislipidemia_diagnosticada", nome="Dislipidemia diagnosticada", tipo_dado="booleano"),

    dict(codigo="sinais_tvp", nome="Sinais/sintomas clínicos de TVP (edema, dor à palpação)", tipo_dado="booleano"),
    dict(codigo="tep_diagnostico_mais_provavel", nome="TEP é o diagnóstico mais provável ou igualmente provável", tipo_dado="booleano"),
    dict(codigo="imobilizacao_ou_cirurgia_recente", nome="Imobilização ≥3 dias ou cirurgia nas últimas 4 semanas", tipo_dado="booleano"),
    dict(codigo="tvp_ou_tep_previo", nome="TVP ou TEP diagnosticados previamente", tipo_dado="booleano"),
    dict(codigo="hemoptise", nome="Hemoptise", tipo_dado="booleano"),
    dict(codigo="malignidade_ativa", nome="Malignidade ativa (tratamento nos últimos 6 meses ou paliativo)", tipo_dado="booleano"),
]
