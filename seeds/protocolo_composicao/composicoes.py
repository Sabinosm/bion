"""Composicoes de exemplo -- protocolos compostos (tipo_protocolo=
'protocolo-composto') montados a partir dos modulos em modulos.py.

Cada composicao e uma lista de (sigla_modulo, papel, grupo_agregacao).
codigo_composicao e calculado, nunca escrito a mao (ver montar_seed.py).

tipo_resultado: campo NOT NULL de ProtocoloCatalogo, enum
('score-numerico', 'categoria-cor', 'nivel-risco', 'binario'). Pensado
originalmente para protocolos de familia unica (NEWS2='score-numerico',
MTS='categoria-cor'). Para composto, nao ha uma unica leitura certa --
cada composicao declara o que melhor descreve a NATUREZA do seu
resultado principal, mesmo quando agregacao='nenhuma' (paralelo):
  - AGB: modulos de naturezas variadas (flag, categoria), sem
    agregacao -- 'nivel-risco' e o mais genérico das 4 opcoes.
  - TSM: tres pontuadores com faixas de gravidade -- 'nivel-risco'
    tambem, porque o resultado nao e um unico score, sao tres.
  - RCV: idem -- RISCO_CV_SIMPLIFICADO e pontuador, mas a composicao
    inteira nao produz um score unico (agregacao='nenhuma').
Se uma composicao futura usar agregacao='soma'/'maximo' sobre um unico
grupo pontuavel, 'score-numerico' passa a ser a leitura mais correta.
"""

COMPOSICAO_AVALIACAO_GERIATRICA = dict(
    sigla_protocolo="AGB",
    nome_protocolo="Avaliação Geriátrica Básica",
    escopo_uso="consulta",
    tipo_resultado="nivel-risco",
    agregacao="nenhuma",
    modulos=[
        ("POLIFARMACIA", "principal", None),
        ("RISCO_QUEDA", "principal", None),
        ("IMC", "principal", None),
        ("PA", "principal", None),
    ],
    regra_gatilho_json=None,
    explicacao_json={
        "o_que_e": "Combinação de módulos de rastreio comuns em avaliação geriátrica: polifarmácia, risco de queda, estado nutricional e pressão arterial.",
        "quando_usar": "Consulta de rotina ou primeira avaliação de pacientes idosos.",
        "como_interpretar": "Cada módulo é lido de forma independente (não há agregação em um score único) — verifique cada resultado e alerta separadamente.",
    },
)

COMPOSICAO_SAUDE_MENTAL = dict(
    sigla_protocolo="TSM",
    nome_protocolo="Triagem de Saúde Mental",
    escopo_uso="consulta",
    tipo_resultado="nivel-risco",
    agregacao="nenhuma",
    modulos=[
        ("ELEGIBILIDADE_ADULTO", "gatilho", None),
        ("PHQ9", "principal", None),
        ("GAD7", "principal", None),
        ("AUDITC", "principal", None),
    ],
    regra_gatilho_json={
        "gatilhos": [{
            "modulo": "ELEGIBILIDADE_ADULTO",
            "quando_classificacao": ["nao_elegivel"],
            "desliga": ["PHQ9", "GAD7", "AUDITC"],
            "motivo": "Instrumentos validados apenas para população adulta (≥18 anos)",
        }]
    },
    explicacao_json={
        "o_que_e": "Combinação de três rastreios de saúde mental validados para adultos: depressão (PHQ-9), ansiedade (GAD-7) e consumo de álcool (AUDIT-C).",
        "quando_usar": "Rastreio de rotina em atenção primária, restrito a pacientes adultos.",
        "como_interpretar": "Cada instrumento é lido de forma independente. Se o paciente for menor de idade, os três rastreios ficam marcados como não aplicáveis (nenhum foi validado para essa faixa etária).",
    },
)

COMPOSICAO_RISCO_CARDIOVASCULAR = dict(
    sigla_protocolo="RCV",
    nome_protocolo="Rastreio de Risco Cardiovascular e Metabólico",
    escopo_uso="consulta",
    tipo_resultado="nivel-risco",
    agregacao="nenhuma",
    modulos=[
        ("RISCO_CV_SIMPLIFICADO", "principal", None),
        ("PA", "principal", None),
        ("IMC", "principal", None),
    ],
    regra_gatilho_json=None,
    explicacao_json={
        "o_que_e": "Combinação de rastreio de fatores de risco cardiovascular, pressão arterial e estado nutricional.",
        "quando_usar": "Consulta de rotina para pacientes adultos, especialmente acima de 40 anos ou com fatores de risco conhecidos.",
        "como_interpretar": "Cada módulo é lido de forma independente. O módulo de risco cardiovascular é uma contagem simplificada de fatores, não um escore de Framingham.",
    },
)

COMPOSICOES = [
    COMPOSICAO_AVALIACAO_GERIATRICA,
    COMPOSICAO_SAUDE_MENTAL,
    COMPOSICAO_RISCO_CARDIOVASCULAR,
]