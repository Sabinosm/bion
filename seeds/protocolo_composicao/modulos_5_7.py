"""Seed: modulos 5 a 7."""

MODULO_AUDITC = dict(
    sigla="AUDITC",
    nome_modulo="AUDIT-C — Rastreio de Consumo de Álcool",
    tipo_modulo="epidemiologico",
    familia_calculo="pontuador",
    tipo_saida="pontos",
    referencia_bibliografica="Bush K, Kivlahan DR, McDonell MB, et al. The AUDIT alcohol consumption questions (AUDIT-C). Arch Intern Med. 1998;158(16):1789-95.",
    versao="1.0",
    campos=[("auditc_item1", True), ("auditc_item2", True), ("auditc_item3", True), ("sexo_biologico", True)],
    # NOTA DE MODELAGEM: soma 3 itens (0-4 cada, total 0-12), mas o ponto
    # de corte depende do sexo biologico (>=4 homens, >=3 mulheres) --
    # por isso usa 'interpretacao segmentada por sexo_biologico' em vez
    # de uma unica faixa. sexo_biologico entra nos campos do modulo mas
    # NAO E somado -- so escolhe qual conjunto de faixas aplicar ao total.
    configuracao_json={
        "familia": "pontuador",
        "parametros": [
            {"variavel": "auditc_item1", "tipo": "mapeamento", "mapa": {"0": 0, "1": 1, "2": 2, "3": 3, "4": 4}},
            {"variavel": "auditc_item2", "tipo": "mapeamento", "mapa": {"0": 0, "1": 1, "2": 2, "3": 3, "4": 4}},
            {"variavel": "auditc_item3", "tipo": "mapeamento", "mapa": {"0": 0, "1": 1, "2": 2, "3": 3, "4": 4}},
        ],
        "interpretacao": {
            "segmentada_por": "sexo_biologico",
            "por_valor": {
                "masculino": {"faixas": [
                    {"min": None, "max": 4, "classificacao": "sem_indicacao_de_risco", "gravidade": 0},
                    {"min": 4, "max": None, "classificacao": "consumo_de_risco", "gravidade": 1},
                ]},
                "feminino": {"faixas": [
                    {"min": None, "max": 3, "classificacao": "sem_indicacao_de_risco", "gravidade": 0},
                    {"min": 3, "max": None, "classificacao": "consumo_de_risco", "gravidade": 1},
                ]},
            },
        },
    },
    explicacao_json={
        "o_que_e": "Rastreio de 3 itens para consumo de risco de álcool, derivado do AUDIT completo (OMS).",
        "quando_usar": "Rastreio de rotina em qualquer consulta de atenção primária.",
        "como_interpretar": "Soma dos 3 itens (0 a 12). Ponto de corte diferente por sexo: ≥4 em homens, ≥3 em mulheres indicam consumo de risco.",
        "limitacoes": "Rastreia padrão de consumo, não dependência (não avalia tolerância, abstinência ou perda de controle). Um resultado positivo indica investigação adicional (AUDIT completo), não diagnóstico.",
    },
)

MODULO_POLIFARMACIA = dict(
    sigla="POLIFARMACIA",
    nome_modulo="Alerta de Polifarmácia",
    tipo_modulo="comorbidade",
    familia_calculo="regra",
    tipo_saida="flag",
    referencia_bibliografica="Uso corrente na literatura geriátrica: ≥5 medicamentos em uso contínuo como limiar de polifarmácia (ex. Oliveira et al., 2020).",
    versao="1.0",
    campos=[("numero_medicamentos", True)],
    configuracao_json={
        "familia": "regra",
        "condicao": {"variavel": "numero_medicamentos", "op": ">=", "valor": 5},
        "saida_verdadeiro": {"classificacao": "alerta_polifarmacia", "motivo": "5 ou mais medicamentos em uso contínuo"},
        "saida_falso": {"classificacao": "sem_alerta"},
    },
    explicacao_json={
        "o_que_e": "Sinaliza uso concomitante de 5 ou mais medicamentos contínuos, associado a maior risco de interações e eventos adversos.",
        "quando_usar": "Qualquer consulta de acompanhamento, especialmente em idosos.",
        "como_interpretar": "Alerta disparado quando o número de medicamentos em uso contínuo é ≥5. Não indica quais medicamentos são problemáticos — motiva revisão da lista completa.",
        "limitacoes": "O limiar de 5 é uma convenção da literatura, não um corte fisiológico exato; polifarmácia apropriada pode existir em quadros multissistêmicos.",
    },
)

MODULO_RISCO_QUEDA = dict(
    sigla="RISCO_QUEDA",
    nome_modulo="Fatores de Risco de Queda",
    tipo_modulo="comorbidade",
    familia_calculo="regra",
    tipo_saida="flag",
    referencia_bibliografica=(
        "Não corresponde a um escore único e validado com nome próprio; "
        "combina fatores de risco objetivos recorrentes na literatura de "
        "quedas em idosos (histórico de queda, marcha alterada, polifarmácia)."
    ),
    versao="1.0",
    campos=[("queda_ultimo_ano", True), ("marcha_alterada", True), ("numero_medicamentos", True)],
    configuracao_json={
        "familia": "regra",
        "condicao": {"ou": [
            {"variavel": "queda_ultimo_ano", "op": "==", "valor": True},
            {"variavel": "marcha_alterada", "op": "==", "valor": True},
            {"variavel": "numero_medicamentos", "op": ">=", "valor": 5},
        ]},
        "saida_verdadeiro": {"classificacao": "risco_aumentado_de_queda", "motivo": "Presença de ao menos um fator de risco objetivo"},
        "saida_falso": {"classificacao": "sem_fator_de_risco_identificado"},
    },
    explicacao_json={
        "o_que_e": "Sinaliza risco aumentado de queda a partir de três fatores objetivos: queda no último ano, marcha/equilíbrio alterados, ou uso de 5+ medicamentos.",
        "quando_usar": "Avaliação de rotina em idosos ou pacientes com mobilidade reduzida.",
        "como_interpretar": "Alerta disparado se qualquer um dos três fatores estiver presente. Não é um escore graduado — é binário (algum fator presente ou nenhum).",
        "limitacoes": "Não é um instrumento validado único (ao contrário do PHQ-9 ou AUDIT-C); é uma combinação de fatores de risco citados na literatura, usada aqui como triagem inicial, não como estratificação de risco quantitativa.",
    },
)
