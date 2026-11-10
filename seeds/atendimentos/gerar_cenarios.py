"""gerar_cenarios.py -- Etapa 1 do seed de atendimentos.

Lê seed_pacientes.csv e escreve seed_atendimentos.json: um bloco por paciente
ATIVO e VIVO (um atendimento para cada um), com o histórico clínico do CSV
(que o loader grava pelo binário) e, em 32 deles, um cenário completo com
queixa, sinais vitais, coleta, input e protocolos. Não toca no banco.

Uso:
    python gerar_cenarios.py
    python gerar_cenarios.py --csv seed_pacientes.csv --saida seed_atendimentos.json
    python gerar_cenarios.py --seed 7 --hoje 2026-11-09 --sem-validar

O resultado é determinístico para o mesmo CSV, --seed e --hoje.

FORMATO DO JSON (contrato com o loader)
  {
    "versao_formato": 1, "gerado_com": {...}, "protocolos": {chave: {uuid, nome}},
    "resumo": {categoria: qtd}, "pacientes": [ <bloco>, ... ]
  }
  bloco (um por paciente), chave de busca = cpf:
    cpf, nome, linha_csv, categoria, cenario
    historico: {alergias, medicamentos, tipo_sanguineo, doenca_cronica}
        cada seção: {"possui": bool, "itens": [...]} (tipo_sanguineo: possui + tipo_sanguineo).
        Os itens seguem os CreateSchemas dos dados. Em alergias, `reacoes_extras`
        NÃO faz parte do schema: o loader as tira do item e as registra depois
        pelo ReacaoAlergiaService.
    atendimento: {"duracao_min": n} nos básicos; nos cenários também:
        queixa_principal, desde_quando_horas, sinais_vitais (SinaisVitaisIn),
        input_json (união das variáveis dos protocolos do caso, ou null),
        valor_avpu, protocolos [uuid], duracao_triagem_min
    reavaliacao: null ou {queixa_principal, desde_quando_horas, sinais_vitais,
        novas_alergias, duracao_min, dias_apos}
    esperado: gabarito para o loader conferir (null nos básicos)
    ordem: posição (1..N) entre os pacientes ativos; é a linha do seed_consultas
    consulta: estado ALVO da consulta, vindo do seed_consultas (cenario,
        origem_encaminhamento, desfecho_final, dias_atras). O loader leva a consulta
        até esse estado:
          em-triagem             triagem aberta, com o binário inserido, NÃO finalizada
          aguardando-medico      triagem finalizada (consulta aguardando o médico)
          em-atendimento         avaliação médica em andamento (protocolos executados)
          encerrada-alta/internacao/transferencia
                                 atendimento(s) finalizado(s) + consulta encerrada
          evasao                 só o binário inserido (nada além disso)
        (aguardando-triagem e encerrada-obito não são gerados: ver SUBSTITUICOES_ESTADO)

CONSULTAS
  O estado de cada consulta é decidido AQUI: o script lê o seed_consultas.csv (80
  linhas), completa até o nº de pacientes ativos (mesma proporção de estados) e
  distribui as linhas entre os pacientes, de modo que cada cenário completo caia
  num estado compatível (encerrada-alta/internacao/transferencia ou em-atendimento).
  Grava seed_consultas_90.csv NA ORDEM DOS PACIENTES ATIVOS (linha i = i-ésimo
  paciente ativo, que é como o seed_consultas.py os associa).

GABARITO (`esperado`) -- só o que não depende da configuração do banco:
  NEWS2: escore_total e override_disparado (exatos) + risco semântico.
  Compostos: `classificacoes_contidas` = classificações que ALGUM módulo deve
  devolver (conferência por subconjunto: não dependo das siglas dos módulos).
"""

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

VERSAO_FORMATO = 1
CSV_PADRAO = Path(__file__).with_name("seed_pacientes.csv")
SAIDA_PADRAO = Path(__file__).with_name("seed_atendimentos.json")
CONSULTAS_PADRAO = Path(__file__).with_name("seed_consultas.csv")
CONSULTAS_SAIDA_PADRAO = Path(__file__).with_name("seed_consultas_90.csv")

PROTOCOLOS = {
    "news2": {"uuid": "41ab91ff-6d62-44cf-96d3-3f4806ca51f5", "nome": "NEWS2"},
    "geriatrica": {"uuid": "d31cf487-e665-42aa-b78e-a39b3f0e8140", "nome": "Avaliação Geriátrica Básica"},
    "saude_mental": {"uuid": "12f508b6-08f9-46e4-8751-df5c86a07f6d", "nome": "Triagem de Saúde Mental"},
    "cardiometabolico": {"uuid": "f3e206b3-af60-4d90-9b22-57ba5210b434",
                         "nome": "Rastreio de Risco Cardiovascular e Metabólico"},
}


# ============================================================================
# Cálculo do gabarito (espelha a configuração dos protocolos enviada)
# ============================================================================
# NEWS2: faixas com limites INCLUSIVOS; vale a primeira faixa que contém o valor.
NEWS2_FAIXAS = {
    "frequencia_respiratoria": [(None, 8, 3), (9, 11, 1), (12, 20, 0), (21, 24, 2), (25, None, 3)],
    "spo2": [(None, 91, 3), (92, 93, 2), (94, 95, 1), (96, None, 0)],
    "temperatura": [(None, 35.1, 3), (35.1, 36.1, 1), (36.1, 38.1, 0), (38.1, 39.1, 1), (39.1, None, 2)],
    "pressao_arterial_sistolica": [(None, 90, 3), (91, 100, 2), (101, 110, 1), (111, 219, 0), (220, None, 3)],
    "frequencia_cardiaca": [(None, 40, 3), (41, 50, 1), (51, 90, 0), (91, 110, 1), (111, 130, 2), (131, None, 3)],
}
NEWS2_ENUMS = {
    "uso_oxigenio_suplementar": {"nao": 0, "sim": 2},
    "nivel_consciencia": {"alerta": 0, "confusao_nova": 3, "voz": 3, "dor": 3, "irresponsivo": 3},
}
AVPU_POR_CONSCIENCIA = {"alerta": "A", "confusao_nova": "C", "voz": "V", "dor": "P", "irresponsivo": "U"}


def calcular_news2(valores: dict) -> dict:
    """Escore total e override (algum parâmetro isolado com 3 pontos)."""
    pontos = {}
    for campo, faixas in NEWS2_FAIXAS.items():
        v = valores[campo]
        for minimo, maximo, pts in faixas:
            if (minimo is None or v >= minimo) and (maximo is None or v <= maximo):
                pontos[campo] = pts
                break
        else:
            raise ValueError(f"NEWS2: {campo}={v} fora das faixas (use inteiros nos campos inteiros)")
    for campo, mapa in NEWS2_ENUMS.items():
        pontos[campo] = mapa[valores[campo]]
    total = sum(pontos.values())
    override = any(p >= 3 for p in pontos.values())
    risco = "alto" if total >= 7 else ("medio" if (total >= 5 or override) else "baixo")
    return {"escore_total": total, "override_disparado": override, "risco": risco}


def cls_imc(imc: float) -> str:
    if imc < 18.5:
        return "baixo_peso"
    if imc < 25:
        return "eutrofico"
    if imc < 30:
        return "sobrepeso"
    if imc < 35:
        return "obesidade_grau_1"
    if imc < 40:
        return "obesidade_grau_2"
    return "obesidade_grau_3"


def cls_pa(sis: float, dia: float) -> str:
    if sis >= 180 or dia >= 110:
        return "hipertensao_estagio_3"
    if sis >= 160 or dia >= 100:
        return "hipertensao_estagio_2"
    if sis >= 140 or dia >= 90:
        return "hipertensao_estagio_1"
    if sis >= 130 or dia >= 85:
        return "limitrofe"
    return "otima"


def risco_cv(fumante: bool, dm: bool, dislip: bool, idade: int) -> tuple:
    pts = int(fumante) + int(dm) + int(dislip) + (1 if idade >= 45 else 0)
    return pts, ("baixo_risco" if pts < 1 else "risco_moderado" if pts < 3 else "risco_elevado")


def cls_phq9(total: int) -> str:
    return ("minima" if total < 5 else "leve" if total < 10 else "moderada" if total < 15
            else "moderadamente_grave" if total < 20 else "grave")


def cls_gad7(total: int) -> str:
    return "minima" if total < 5 else "leve" if total < 10 else "moderada" if total < 15 else "grave"


def cls_auditc(total: int, sexo: str) -> str:
    corte = 4 if sexo == "masculino" else 3
    return "consumo_de_risco" if total >= corte else "sem_indicacao_de_risco"


# ============================================================================
# Leitura do CSV
# ============================================================================
def _idade(nasc: date, hoje: date) -> int:
    return hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))


def _parse_alergias(composto: str) -> dict:
    """{substancia: [reacao, ...]}. Aceita itens separados por ';' ou '|' (5 campos
    abrem a alergia; 4 campos são reação extra da última)."""
    grupos, atual = {}, None
    for item in re.split(r"[|;]", composto or ""):
        if not item.strip():
            continue
        c = item.split("^")
        if len(c) == 5:
            atual = c[0]
            grupos.setdefault(atual, []).append(
                {"manifestacao": c[1], "gravidade": c[2], "descricao": c[3] or None, "data_ocorrencia": c[4] or None})
        elif len(c) == 4 and atual:
            grupos[atual].append(
                {"manifestacao": c[0], "gravidade": c[1], "descricao": c[2] or None, "data_ocorrencia": c[3] or None})
        else:
            raise ValueError(f"alergias mal formatadas: {item!r}")
    return grupos


def _itens(composto: str) -> list:
    return [i.split("^") for i in (composto or "").split(";") if i]


def carregar_pacientes(caminho: Path, hoje: date) -> list:
    with open(caminho, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    pacientes = []
    for i, row in enumerate(rows):
        peso = float(row["peso"]) if row["peso"] else None
        altura = int(row["altura"]) if row["altura"] else None
        doencas = [{"codigo_cid10": c[0], "descricao_cid10": c[1], "desde": c[2],
                    "status": c[3], "observacoes": c[4] or None}
                   for c in _itens(row["doencas_cronicas"])]
        meds = [{"descricao": c[0], "dose": c[1] or None, "frequencia": c[2] or None, "desde": c[3] or None}
                for c in _itens(row["medicamentos_em_uso"])]
        nasc = date.fromisoformat(row["data_nascimento"])
        pacientes.append({
            "linha": i + 2, "row": row, "nome": row["nome_completo"], "cpf": row["cpf"],
            "sexo": row["sexo_biologico"], "idade": _idade(nasc, hoje),
            "ativo": row["status"] == "ativo" and row["falecido"].strip().lower() not in ("1", "true", "t", "sim"),
            "peso": peso, "altura": altura,
            "imc": round(peso / ((altura / 100) ** 2), 1) if peso and altura else None,
            "doencas": doencas, "cids": [d["codigo_cid10"] for d in doencas],
            "meds": meds, "meds_extra": [],
            "alergias": _parse_alergias(row["alergias"]),
            "tipo": row["tipo_sanguineo"] or None,
        })
    return pacientes


def montar_historico(p: dict) -> dict:
    itens_alergia = []
    for substancia, reacoes in p["alergias"].items():
        primeira, extras = reacoes[0], reacoes[1:]
        itens_alergia.append({
            "substancia": substancia, "flag_confirmado": True,
            "tipo_reacao": primeira["manifestacao"], "gravidade": primeira["gravidade"],
            "descricao_reacao": primeira["descricao"],
            "reacoes_extras": [{"manifestacao": r["manifestacao"], "gravidade": r["gravidade"],
                                "descricao": r["descricao"], "data_ocorrencia": r["data_ocorrencia"]}
                               for r in extras],
        })
    meds = p["meds"] + p["meds_extra"]
    return {
        "alergias": {"possui": bool(itens_alergia), "itens": itens_alergia},
        "medicamentos": {"possui": bool(meds), "itens": meds},
        "tipo_sanguineo": {"possui": True, "tipo_sanguineo": p["tipo"] or "desconhecido"},
        "doenca_cronica": {"possui": bool(p["doencas"]), "itens": p["doencas"]},
    }


# ============================================================================
# Sinais vitais
# ============================================================================
_VITAIS = [("pa-sistolica", "pas", "mmHg"), ("pa-diastolica", "pad", "mmHg"),
           ("frequencia-cardiaca", "fc", "bpm"), ("frequencia-respiratoria", "fr", "irpm"),
           ("spo2", "spo2", "%"), ("temperatura", "temp", "°C"), ("glicemia-capilar", "glic", "mg-dL")]
_SITIO = {"pa-sistolica": "manguito-braco-esquerdo", "pa-diastolica": "manguito-braco-esquerdo",
          "spo2": "oximetria-digital", "temperatura": "axilar"}


def montar_sinais(v: dict) -> list:
    sinais = []
    for tipo, chave, unidade in _VITAIS:
        if v.get(chave) is None:
            continue
        s = {"tipo_parametro": tipo, "valor_numerico": v[chave], "unidade": unidade}
        if tipo in _SITIO:
            s["sitio_medicao"] = _SITIO[tipo]
        sinais.append(s)
    return sinais


def com_variacao(rng: random.Random, base: dict) -> dict:
    """Pequena variação nos valores de cenários livres (não nos de protocolo)."""
    v = dict(base)
    for k in ("pas", "pad", "fc", "fr"):
        if v.get(k) is not None:
            v[k] = v[k] + rng.randint(-3, 3)
    if v.get("spo2") is not None:
        v["spo2"] = max(80, min(100, v["spo2"] + rng.randint(-1, 1)))
    if v.get("temp") is not None:
        v["temp"] = round(v["temp"] + rng.choice([-0.2, -0.1, 0, 0.1, 0.2]), 1)
    return v


NORMAL = {"pas": 122, "pad": 78, "fc": 76, "fr": 16, "spo2": 98, "temp": 36.7}

# ============================================================================
# Cenários (textos e perfis de sinais vitais)
# ============================================================================
CONFLITO_ALERGIA = {
    "Penicilina": dict(
        queixa="Dor de garganta forte com placas brancas e febre há 3 dias.", horas=72,
        vitais={**NORMAL, "fc": 98, "temp": 38.6},
        esperado={"hipotese": "faringoamigdalite bacteriana", "evitar": ["penicilina", "amoxicilina", "ampicilina"]}),
    "Sulfametoxazol": dict(
        queixa="Ardência ao urinar, urgência e dor em baixo ventre há 2 dias.", horas=48,
        vitais={**NORMAL, "fc": 84, "temp": 37.4},
        esperado={"hipotese": "infecção urinária", "evitar": ["sulfametoxazol", "sulfametoxazol-trimetoprima"]}),
    "Dipirona": dict(
        queixa="Febre e dor de cabeça desde ontem.", horas=24,
        vitais={**NORMAL, "fc": 92, "temp": 38.3},
        esperado={"hipotese": "síndrome gripal", "evitar": ["dipirona", "metamizol"]}),
    "AAS": dict(
        queixa="Dor de cabeça intensa e febre há 1 dia.", horas=24,
        vitais={**NORMAL, "fc": 90, "temp": 38.1},
        esperado={"hipotese": "síndrome gripal", "evitar": ["AAS", "ácido acetilsalicílico"]}),
}

# `inicial` = queixa do 1º atendimento (antes da reação); o resto é a alergia nova,
# registrada na reavaliação.
NOVAS_ALERGIAS = [
    dict(substancia="Amoxicilina", tipo_reacao="cutanea", gravidade="moderada",
         descricao_reacao="Manchas vermelhas e coceira pelo corpo no segundo dia de tratamento.",
         inicial=dict(queixa="Dor de garganta e febre baixa há 2 dias.", horas=48, vitais={**NORMAL, "fc": 88, "temp": 37.9})),
    dict(substancia="Dipirona", tipo_reacao="cutanea", gravidade="leve",
         descricao_reacao="Urticária leve poucas horas após a primeira dose.",
         inicial=dict(queixa="Febre e dor no corpo desde ontem.", horas=24, vitais={**NORMAL, "fc": 94, "temp": 38.2})),
    dict(substancia="Ibuprofeno", tipo_reacao="respiratoria", gravidade="moderada",
         descricao_reacao="Falta de ar e chiado após tomar o comprimido.",
         inicial=dict(queixa="Dor nas costas após carregar peso, há 3 dias.", horas=72, vitais=NORMAL)),
    dict(substancia="Cefalexina", tipo_reacao="cutanea", gravidade="leve",
         descricao_reacao="Exantema pruriginoso no tronco após três doses.",
         inicial=dict(queixa="Ferida no pé com vermelhidão e secreção há 4 dias.", horas=96, vitais={**NORMAL, "temp": 37.6})),
]

ACOMPANHAMENTO = {
    "M17": dict(queixa="Dor no joelho ao subir escadas, pior no fim do dia.", horas=720),
    "M54": dict(queixa="Dor lombar persistente, piora quando fica muito tempo sentado.", horas=336),
    "L40": dict(queixa="Placas descamativas nos cotovelos com coceira.", horas=480),
    "E04": dict(queixa="Retorno para acompanhar o nódulo da tireoide, sem queixas novas.", horas=None),
    "G40": dict(queixa="Retorno de rotina, sem crises no último mês.", horas=None),
    "K21": dict(queixa="Azia e queimação após as refeições, mais à noite.", horas=360),
    "F33": dict(queixa="Retorno para acompanhamento, refere sono irregular.", horas=None),
}

INTERACAO = {
    "aas": dict(
        queixa="Dor no joelho e nas costas há 5 dias; quer tomar ibuprofeno por conta própria.", horas=120,
        vitais={**NORMAL, "pas": 128},
        esperado={"tipo": "interacao", "em_uso": "AAS", "risco": "AINE + AAS: risco de sangramento"}),
    "renal": dict(
        queixa="Dor lombar forte há 3 dias; tomou diclofenaco emprestado de um vizinho.", horas=72,
        vitais={**NORMAL, "pas": 134, "pad": 84},
        esperado={"tipo": "interacao", "em_uso": "anti-hipertensivo/diurético + doença renal crônica",
                  "risco": "AINE: piora da função renal"}),
    "fluoxetina": dict(
        queixa="Dor forte na coluna há uma semana; pede um remédio mais forte.", horas=168,
        vitais={**NORMAL, "pas": 126},
        esperado={"tipo": "interacao", "em_uso": "Fluoxetina", "risco": "tramadol: síndrome serotoninérgica"}),
    "hipoglicemiante": dict(
        queixa="Tontura, suor frio e tremores há 2 horas após pular o almoço.", horas=2,
        vitais={**NORMAL, "fc": 102, "glic": 52},
        esperado={"tipo": "efeito_adverso", "em_uso": "sulfonilureia/insulina", "risco": "hipoglicemia"}),
}

# ============================================================================
# Casos de protocolo
# ============================================================================
def _caso_protocolo(chave, p, cenario, queixa, horas, vitais, input_json, avpu, esperado):
    return {
        "categoria": "protocolo", "cenario": cenario, "paciente": p,
        "atendimento": {
            "queixa_principal": queixa, "desde_quando_horas": horas,
            "sinais_vitais": montar_sinais(vitais), "input_json": input_json, "valor_avpu": avpu,
            "protocolos": [PROTOCOLOS[chave]["uuid"]],
        },
        "esperado": {"protocolos": {PROTOCOLOS[chave]["uuid"]: esperado}},
    }


def caso_news2(p, cenario, queixa, horas, v, o2, consciencia):
    entrada = {"frequencia_respiratoria": v["fr"], "spo2": v["spo2"], "uso_oxigenio_suplementar": o2,
               "temperatura": v["temp"], "pressao_arterial_sistolica": v["pas"],
               "frequencia_cardiaca": v["fc"], "nivel_consciencia": consciencia}
    return _caso_protocolo("news2", p, cenario, queixa, horas, v, entrada,
                           AVPU_POR_CONSCIENCIA[consciencia], {"nome": "NEWS2", **calcular_news2(entrada)})


def caso_cardiometabolico(p, cenario, queixa, horas, v, fumante):
    dm = any(c.startswith("E11") for c in p["cids"])
    dislip = any(c.startswith("E78") for c in p["cids"])
    entrada = {"pa_sistolica": v["pas"], "pa_diastolica": v["pad"], "fumante_atual": fumante,
               "diabetes_diagnosticado": dm, "dislipidemia_diagnosticada": dislip, "idade": p["idade"]}
    classes = [cls_pa(v["pas"], v["pad"]), risco_cv(fumante, dm, dislip, p["idade"])[1]]
    if p["imc"] is not None:
        entrada["imc"] = p["imc"]
        classes.append(cls_imc(p["imc"]))
    return _caso_protocolo("cardiometabolico", p, cenario, queixa, horas, v, entrada, None,
                           {"nome": PROTOCOLOS["cardiometabolico"]["nome"], "classificacoes_contidas": sorted(set(classes)),
                            "pontos_risco": risco_cv(fumante, dm, dislip, p["idade"])[0]})


def caso_saude_mental(p, cenario, queixa, horas, v, phq, gad, audit):
    sexo = {"M": "masculino", "F": "feminino"}.get(p["sexo"])
    entrada = {"idade": p["idade"]}
    if sexo:
        entrada["sexo_biologico"] = sexo
    for i, x in enumerate(phq, 1):
        entrada[f"phq9_item{i}"] = str(x)
    for i, x in enumerate(gad, 1):
        entrada[f"gad7_item{i}"] = str(x)
    for i, x in enumerate(audit, 1):
        entrada[f"auditc_item{i}"] = str(x)
    elegivel = p["idade"] >= 18
    if elegivel:
        classes = [cls_phq9(sum(phq)), cls_gad7(sum(gad)), cls_auditc(sum(audit), sexo), "elegivel"]
        aviso = None
    else:
        # menor de 18: só a elegibilidade é garantida (um gatilho pode desligar os outros módulos)
        classes = ["nao_elegivel"]
        aviso = "menor de 18: os demais módulos dependem do gatilho cadastrado no banco"
    esperado = {"nome": PROTOCOLOS["saude_mental"]["nome"], "classificacoes_contidas": sorted(set(classes))}
    if aviso:
        esperado["aviso"] = aviso
    return _caso_protocolo("saude_mental", p, cenario, queixa, horas, v, entrada, None, esperado)


def caso_geriatrico(p, cenario, queixa, horas, v, queda, marcha):
    n_meds = len(p["meds"]) + len(p["meds_extra"])
    entrada = {"pa_sistolica": v["pas"], "pa_diastolica": v["pad"], "numero_medicamentos": n_meds,
               "queda_ultimo_ano": queda, "marcha_alterada": marcha}
    classes = [cls_pa(v["pas"], v["pad"]),
               "alerta_polifarmacia" if n_meds >= 5 else "sem_alerta",
               "risco_aumentado_de_queda" if (queda or marcha or n_meds >= 5) else "sem_fator_de_risco_identificado"]
    if p["imc"] is not None:
        entrada["imc"] = p["imc"]
        classes.append(cls_imc(p["imc"]))
    return _caso_protocolo("geriatrica", p, cenario, queixa, horas, v, entrada, None,
                           {"nome": PROTOCOLOS["geriatrica"]["nome"], "classificacoes_contidas": sorted(set(classes))})


# ============================================================================
# Seleção dos pacientes e montagem dos 32 cenários
# ============================================================================
class Seletor:
    def __init__(self, pacientes, rng):
        self.pool = [p for p in pacientes if p["ativo"]]
        self.usados = set()
        self.rng = rng
        self.avisos = []

    def pegar(self, rotulo, *preferencias):
        """Primeiro predicado (em ordem de preferência) que ainda tem candidato."""
        for pred in preferencias:
            candidatos = [p for p in self.pool if p["linha"] not in self.usados and pred(p)]
            if candidatos:
                escolhido = self.rng.choice(candidatos)
                self.usados.add(escolhido["linha"])
                return escolhido
        self.avisos.append(f"sem paciente disponível para: {rotulo}")
        return None


def _cid(prefixo):
    return lambda p: any(c.startswith(prefixo) for c in p["cids"])


def _adulto(p):
    return p["idade"] >= 18


def _sem_doenca(p):
    return _adulto(p) and not p["cids"]


def _com_imc(p):
    return p["imc"] is not None


def _med(nome):
    return lambda p: any(m["descricao"] == nome for m in p["meds"])


def _alergico(substancia):
    return lambda p: substancia in p["alergias"]


def _sem_alergia(p):
    return _adulto(p) and not p["alergias"]


def montar_cenarios(pacientes, rng):
    s = Seletor(pacientes, rng)
    casos = []

    def add(caso):
        if caso is not None:
            casos.append(caso)

    # ---- Saúde mental (3) ----
    p = s.pegar("saúde mental: mínima", lambda p: _sem_doenca(p) and p["sexo"] in "MF" and p["idade"] < 60,
                lambda p: _sem_doenca(p) and p["sexo"] in "MF")
    if p:
        add(caso_saude_mental(p, "saude_mental_minima", "Quer uma avaliação preventiva de saúde mental, sem queixas importantes.",
                              None, com_variacao(rng, NORMAL), [0, 1, 0, 1, 0, 0, 0, 0, 0], [1, 0, 1, 0, 0, 0, 0], [1, 0, 0]))
    p = s.pegar("saúde mental: moderada", lambda p: _cid("F33")(p) and _adulto(p) and p["sexo"] in "MF",
                lambda p: _adulto(p) and p["sexo"] in "MF")
    if p:
        add(caso_saude_mental(p, "saude_mental_moderada", "Tristeza, cansaço e dificuldade para dormir há semanas.",
                              504, com_variacao(rng, NORMAL), [2, 2, 2, 2, 2, 1, 1, 1, 0], [2, 2, 2, 2, 1, 1, 1], [2, 1, 1]))
    p = s.pegar("saúde mental: menor de 18", lambda p: p["idade"] in range(12, 18), lambda p: p["idade"] < 18)
    if p:
        add(caso_saude_mental(p, "saude_mental_menor", "Responsável relata desânimo e queda no rendimento escolar.",
                              336, com_variacao(rng, {**NORMAL, "pas": 108, "pad": 68, "fc": 82}),
                              [1, 1, 0, 1, 0, 0, 0, 0, 0], [1, 0, 0, 1, 0, 0, 0], [0, 0, 0]))

    # ---- Cardiometabólico (3) ----
    p = s.pegar("cardiometabólico: elevado", lambda p: _cid("E11")(p) and _com_imc(p) and p["idade"] >= 45,
                lambda p: _cid("E11")(p) and p["idade"] >= 45)
    if p:
        add(caso_cardiometabolico(p, "cardiometabolico_elevado", "Sede intensa, urina em excesso e visão turva há 5 dias.",
                                  120, {**NORMAL, "pas": 184, "pad": 112, "fc": 96, "glic": 286}, fumante=True))
    p = s.pegar("cardiometabólico: moderado", lambda p: (_cid("I10")(p) or _cid("E78")(p)) and _com_imc(p),
                lambda p: _cid("I10")(p) or _cid("E78")(p))
    if p:
        add(caso_cardiometabolico(p, "cardiometabolico_moderado", "Dor de cabeça na nuca e tontura há 3 dias; pressão alta nas medidas de casa.",
                                  72, {**NORMAL, "pas": 166, "pad": 102, "fc": 84}, fumante=True))
    p = s.pegar("cardiometabólico: baixo", lambda p: _sem_doenca(p) and _com_imc(p) and p["idade"] < 45,
                lambda p: _sem_doenca(p) and _com_imc(p))
    if p:
        add(caso_cardiometabolico(p, "cardiometabolico_baixo", "Quer fazer um check-up de rotina, sem queixas.",
                                  None, {**NORMAL, "pas": 116, "pad": 74, "fc": 72}, fumante=False))

    # ---- Geriátrico (3) ----
    p = s.pegar("geriátrico: polifarmácia", lambda p: p["idade"] >= 65 and _com_imc(p))
    if p:
        p["meds_extra"] = _meds_extra(p)
        add(caso_geriatrico(p, "geriatrico_polifarmacia", "Anda devagar e inseguro, usa vários remédios e sente tontura.",
                            720, {**NORMAL, "pas": 148, "pad": 92, "fc": 80}, queda=False, marcha=True))
    p = s.pegar("geriátrico: queda", lambda p: p["idade"] >= 65 and _com_imc(p))
    if p:
        add(caso_geriatrico(p, "geriatrico_queda", "Caiu duas vezes no banheiro nos últimos meses.",
                            1440, {**NORMAL, "pas": 132, "pad": 80, "fc": 74}, queda=True, marcha=False))
    p = s.pegar("geriátrico: sem fator", lambda p: p["idade"] >= 65 and _com_imc(p) and len(p["meds"]) < 3)
    if p:
        add(caso_geriatrico(p, "geriatrico_sem_fator", "Avaliação geral de rotina, sem queixas.",
                            None, {**NORMAL, "pas": 118, "pad": 76, "fc": 70}, queda=False, marcha=False))

    # ---- NEWS2 (3) ----
    p = s.pegar("NEWS2: baixo", _sem_doenca)
    if p:
        add(caso_news2(p, "news2_baixo", "Dor de cabeça leve, sem outros sintomas.", 24,
                       {"pas": 124, "pad": 80, "fc": 76, "fr": 16, "spo2": 98, "temp": 36.8}, "nao", "alerta"))
    p = s.pegar("NEWS2: médio", _sem_doenca)
    if p:
        add(caso_news2(p, "news2_medio", "Febre e tosse com catarro há 3 dias.", 72,
                       {"pas": 108, "pad": 70, "fc": 104, "fr": 22, "spo2": 94, "temp": 38.4}, "nao", "alerta"))
    p = s.pegar("NEWS2: alto", _sem_doenca)
    if p:
        add(caso_news2(p, "news2_alto", "Falta de ar importante, febre alta e muito cansaço há 2 dias.", 48,
                       {"pas": 98, "pad": 62, "fc": 112, "fr": 24, "spo2": 92, "temp": 38.8}, "sim", "alerta"))

    # ---- Conflito com alergia registrada (5) ----
    for substancia in ("Penicilina", "Penicilina", "Sulfametoxazol", "Sulfametoxazol"):
        p = s.pegar(f"conflito: {substancia}", _alergico(substancia))
        if p:
            add(_caso_livre("conflito_alergia", f"conflito_{substancia.lower()}", p, CONFLITO_ALERGIA[substancia], rng,
                            extra={"alergia": substancia}))
    for substancia in ("Dipirona", "AAS"):
        p = s.pegar(f"conflito: {substancia}", _alergico(substancia))
        if p:
            add(_caso_livre("conflito_alergia", f"conflito_{substancia.lower()}", p, CONFLITO_ALERGIA[substancia], rng,
                            extra={"alergia": substancia}))
            break

    # ---- Interação / efeito adverso de medicamento (4) ----
    for chave, preds in (
            ("aas", [_med("AAS")]),
            ("renal", [lambda p: _cid("N18")(p) and (_med("Hidroclorotiazida")(p) or _med("Furosemida")(p)
                                                      or _med("Losartana")(p)), _cid("N18")]),
            ("fluoxetina", [_med("Fluoxetina")]),
            ("hipoglicemiante", [lambda p: _med("Glibenclamida")(p) or _med("Insulina NPH")(p), _med("Metformina")])):
        p = s.pegar(f"interação: {chave}", *preds)
        if p:
            add(_caso_livre("interacao_medicamentosa", f"interacao_{chave}", p, INTERACAO[chave], rng))

    # ---- Alergia não registrada (4, com reavaliação) ----
    for nova in NOVAS_ALERGIAS:
        p = s.pegar(f"alergia não registrada: {nova['substancia']}", _sem_alergia)
        if p:
            inicial = nova["inicial"]
            alergia_nova = {k: v for k, v in nova.items() if k != "inicial"}
            caso = _caso_livre(
                "alergia_nao_registrada", f"alergia_nova_{nova['substancia'].lower()}", p,
                dict(queixa=inicial["queixa"], horas=inicial["horas"], vitais=inicial["vitais"],
                     esperado={"tipo": "alergia_nova", "substancia": nova["substancia"]}), rng)
            caso["reavaliacao"] = {
                "queixa_principal": f"Retorna com manchas e sintomas após usar o medicamento ({nova['substancia']}).",
                "desde_quando_horas": 24,
                "sinais_vitais": montar_sinais(com_variacao(rng, {**NORMAL, "fc": 90})),
                "novas_alergias": [{**alergia_nova, "flag_confirmado": True}],
                "duracao_min": rng.randint(10, 25), "dias_apos": 1,
            }
            add(caso)

    # ---- Acompanhamento crônico sem protocolo (5) ----
    for prefixo in ("M17", "M54", "L40", "E04", "G40"):
        p = s.pegar(f"acompanhamento: {prefixo}", lambda p, pre=prefixo: _cid(pre)(p) and _adulto(p))
        if p:
            add(_caso_livre("acompanhamento_cronico", f"acompanhamento_{prefixo.lower()}", p,
                            dict(queixa=ACOMPANHAMENTO[prefixo]["queixa"], horas=ACOMPANHAMENTO[prefixo]["horas"],
                                 vitais=NORMAL, esperado={"tipo": "acompanhamento", "cid": prefixo}), rng))

    # ---- Queixa vaga, sem protocolo (2) ----
    p = s.pegar("queixa vaga: adulto", _sem_doenca)
    if p:
        add(_caso_livre("queixa_vaga", "queixa_vaga_adulto", p,
                        dict(queixa="Cansaço e mal-estar geral há alguns dias, sem saber explicar.", horas=96,
                             vitais=NORMAL, esperado={"tipo": "queixa_vaga"}), rng))
    p = s.pegar("queixa vaga: criança", lambda p: p["idade"] < 12, lambda p: p["idade"] < 18)
    if p:
        add(_caso_livre("queixa_vaga", "queixa_vaga_crianca", p,
                        dict(queixa="Dor de barriga e indisposição há 2 dias.", horas=48,
                             vitais={**NORMAL, "pas": 100, "pad": 62, "fc": 88}, esperado={"tipo": "queixa_vaga"}), rng))
    return casos, s


def _meds_extra(p) -> list:
    """Completa a lista até 5 medicamentos (polifarmácia)."""
    ja = {m["descricao"] for m in p["meds"]}
    candidatos = [("Losartana", "50mg", "1x ao dia"), ("Omeprazol", "20mg", "1x ao dia, em jejum"),
                  ("Sinvastatina", "20mg", "1x à noite"), ("Amlodipina", "5mg", "1x ao dia"),
                  ("Levotiroxina", "75mcg", "1x ao dia, em jejum"), ("Paracetamol", "750mg", "se dor, até 3x ao dia")]
    extras = []
    for i, (nome, dose, freq) in enumerate(c for c in candidatos if c[0] not in ja):
        if len(p["meds"]) + len(extras) >= 5:
            break
        extras.append({"descricao": nome, "dose": dose, "frequencia": freq, "desde": f"{2021 + i % 4}-0{3 + i % 6}-15"})
    return extras


def _caso_livre(categoria, cenario, p, modelo, rng, extra=None):
    esperado = dict(modelo["esperado"])
    if extra:
        esperado.update(extra)
    return {
        "categoria": categoria, "cenario": cenario, "paciente": p,
        "atendimento": {
            "queixa_principal": modelo["queixa"], "desde_quando_horas": modelo["horas"],
            "sinais_vitais": montar_sinais(com_variacao(rng, modelo["vitais"])),
            "input_json": None, "valor_avpu": None, "protocolos": [],
        },
        "esperado": esperado,
    }


# ============================================================================
# Montagem do JSON final
# ============================================================================
# ---------------------------------------------------------------------------
# Consultas: estado alvo de cada paciente (vem do seed_consultas.csv)
# ---------------------------------------------------------------------------
COLUNAS_CONSULTA = ["cenario", "origem_encaminhamento", "desfecho_final", "dias_atras"]
# Estados em que o cenário completo (queixa, sinais, input, protocolo) faz sentido.
COMPATIVEIS = ("encerrada-alta", "em-atendimento", "encerrada-internacao", "encerrada-transferencia")
PREFERENCIA = {  # cenário (prefixo) -> estados preferidos, em ordem
    "alergia_nova": ("encerrada-alta",),  # precisa fechar o 1º atendimento para reavaliar
    "news2_alto": ("encerrada-internacao", "em-atendimento", "encerrada-alta"),
    "news2_medio": ("em-atendimento", "encerrada-alta"),
    "cardiometabolico_elevado": ("encerrada-transferencia", "encerrada-internacao", "em-atendimento"),
}
ESTRITO = {"alergia_nova"}  # sem fallback para outros estados
# Estados do CSV original que este seed não usa -> (estado novo, desfecho novo).
SUBSTITUICOES_ESTADO = {
    "aguardando-triagem": ("em-triagem", None),             # consulta sem profissional: vira triagem aberta
    "encerrada-obito": ("encerrada-internacao", "internacao"),  # óbito fora do escopo por ora
}


def carregar_consultas(caminho: Path) -> list:
    with open(caminho, newline="", encoding="utf-8") as f:
        linhas = [{"cenario": r["cenario"].strip(), "origem_encaminhamento": r["origem_encaminhamento"].strip(),
                   "desfecho_final": r["desfecho_final"].strip() or None, "dias_atras": int(r["dias_atras"])}
                  for r in csv.DictReader(f)]
    for l in linhas:
        if l["cenario"] in SUBSTITUICOES_ESTADO:
            l["cenario"], l["desfecho_final"] = SUBSTITUICOES_ESTADO[l["cenario"]]
    return linhas


def completar_consultas(linhas: list, n: int, rng: random.Random) -> list:
    """Ajusta para n linhas mantendo a proporção de estados (maior resto)."""
    if n <= len(linhas):
        return rng.sample(linhas, n)
    base = Counter(l["cenario"] for l in linhas)
    ideal = {c: base[c] * n / len(linhas) for c in base}
    alvo = {c: int(v) for c, v in ideal.items()}
    for c in sorted(base, key=lambda c: ideal[c] - alvo[c], reverse=True)[: n - sum(alvo.values())]:
        alvo[c] += 1
    novas = []
    for c in base:
        modelos = [l for l in linhas if l["cenario"] == c]
        dias = [m["dias_atras"] for m in modelos]
        for _ in range(alvo[c] - base[c]):
            nova = dict(rng.choice(modelos))
            if nova["dias_atras"] > 0:
                nova["dias_atras"] = rng.randint(min(dias), max(dias))
            novas.append(nova)
    return list(linhas) + novas


def _preferencia(cenario: str) -> tuple:
    for prefixo, estados in PREFERENCIA.items():
        if cenario.startswith(prefixo):
            return estados if prefixo in ESTRITO else estados + COMPATIVEIS
    return COMPATIVEIS


def atribuir_consultas(casos: list, ativos: list, linhas: list, rng: random.Random):
    """Devolve ({linha_csv: linha_consulta}, avisos). Cenários completos primeiro, em
    estados compatíveis; o resto dos pacientes recebe as linhas que sobraram."""
    por_estado = defaultdict(list)
    for l in linhas:
        por_estado[l["cenario"]].append(l)
    for lista in por_estado.values():
        rng.shuffle(lista)
    atrib, avisos = {}, []

    def prioridade(c):
        return 0 if c["cenario"].startswith("alergia_nova") else 1 if c["cenario"].startswith("news2_alto") else 2

    for caso in sorted(casos, key=prioridade):
        linha = caso["paciente"]["linha"]
        for estado in _preferencia(caso["cenario"]):
            if por_estado[estado]:
                atrib[linha] = por_estado[estado].pop()
                break
        else:
            avisos.append(f"{caso['cenario']} (linha {linha}): sem estado compatível disponível")
    sobras = [l for lista in por_estado.values() for l in lista]
    rng.shuffle(sobras)
    for p in ativos:
        if p["linha"] not in atrib:
            atrib[p["linha"]] = sobras.pop()
    return atrib, avisos


def montar_json(pacientes, casos, consultas, rng, args, avisos) -> dict:
    por_linha = {c["paciente"]["linha"]: c for c in casos}
    blocos, resumo = [], {}
    for ordem, p in enumerate((x for x in pacientes if x["ativo"]), 1):
        caso = por_linha.get(p["linha"])
        consulta = consultas[p["linha"]]
        categoria = caso["categoria"] if caso else "basico"
        resumo[categoria] = resumo.get(categoria, 0) + 1
        atendimento = dict(caso["atendimento"]) if caso else {}
        atendimento["duracao_min"] = rng.randint(10, 40)
        if caso:
            atendimento["duracao_triagem_min"] = rng.randint(4, 12)
            if caso.get("reavaliacao"):  # a reavaliação não pode cair no futuro
                caso["reavaliacao"]["dias_apos"] = rng.randint(1, max(1, min(5, consulta["dias_atras"] - 1)))
        blocos.append({
            "cpf": p["cpf"], "nome": p["nome"], "linha_csv": p["linha"],
            "categoria": categoria, "cenario": caso["cenario"] if caso else "basico",
            "historico": montar_historico(p),
            "atendimento": atendimento,
            "reavaliacao": caso.get("reavaliacao") if caso else None,
            "esperado": caso["esperado"] if caso else None,
            "ordem": ordem,
            "consulta": consulta,
        })
    return {
        "versao_formato": VERSAO_FORMATO,
        "gerado_com": {"seed": args.seed, "hoje": args.hoje.isoformat(), "csv": Path(args.csv).name,
                       "avisos": avisos},
        "protocolos": PROTOCOLOS, "resumo": dict(sorted(resumo.items())), "pacientes": blocos,
    }


# ============================================================================
# Validação contra os schemas reais do projeto
# ============================================================================
def _importar_schemas():
    from src.domains.paciente.schemas.schema_alergia import AlergiaCreateSchema, ReacaoAlergiaCreateSchema
    from src.domains.paciente.schemas.schema_doenca_cronica import DoencaCronicaCreateSchema
    from src.domains.paciente.schemas.schema_medicamento_em_uso import MedicamentoEmUsoCreateSchema
    from src.domains.paciente.schemas.schema_tipo_sanguineo import ObservacaoTipoSanguineoCreateSchema
    from src.domains.dados_clinicos.schema import SinaisVitaisIn, ColetaClinicaIn, InputProtocoloIn
    return dict(alergia=AlergiaCreateSchema, reacao=ReacaoAlergiaCreateSchema, doenca=DoencaCronicaCreateSchema,
                medicamento=MedicamentoEmUsoCreateSchema, tipo=ObservacaoTipoSanguineoCreateSchema,
                sinais=SinaisVitaisIn, coleta=ColetaClinicaIn, input=InputProtocoloIn)


def validar_schemas(dados: dict) -> list:
    """Valida cada item do JSON com os schemas de entrada reais. Devolve a lista de erros."""
    sch = _importar_schemas()
    erros = []

    def ok(rotulo, schema, corpo):
        try:
            schema(**corpo)
        except Exception as e:  # ValidationError do pydantic
            erros.append(f"{rotulo}: {str(e).splitlines()[0:3]}")

    for b in dados["pacientes"]:
        r, h = f"linha {b['linha_csv']} ({b['nome']})", b["historico"]
        for it in h["alergias"]["itens"]:
            ok(f"{r} alergia", sch["alergia"], {k: v for k, v in it.items() if k != "reacoes_extras"})
            for ex in it["reacoes_extras"]:
                ok(f"{r} reação extra", sch["reacao"], ex)
        for it in h["doenca_cronica"]["itens"]:
            ok(f"{r} doença", sch["doenca"], it)
        for it in h["medicamentos"]["itens"]:
            ok(f"{r} medicamento", sch["medicamento"], it)
        ok(f"{r} tipo sanguíneo", sch["tipo"], {"tipo_sanguineo": h["tipo_sanguineo"]["tipo_sanguineo"]})
        a = b["atendimento"]
        if a.get("sinais_vitais"):
            ok(f"{r} sinais vitais", sch["sinais"], {"sinais": a["sinais_vitais"]})
            ok(f"{r} coleta", sch["coleta"], {"desde_quando_sintomas": a["desde_quando_horas"]})
            ok(f"{r} input", sch["input"], {k: v for k, v in {
                "input_json": a["input_json"], "queixa_principal": a["queixa_principal"],
                "valor_avpu": a["valor_avpu"]}.items() if v is not None})
        rv = b["reavaliacao"]
        if rv:
            ok(f"{r} reavaliação sinais", sch["sinais"], {"sinais": rv["sinais_vitais"]})
            for al in rv["novas_alergias"]:
                ok(f"{r} nova alergia", sch["alergia"], al)
    return erros


# ============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(CSV_PADRAO))
    ap.add_argument("--saida", default=str(SAIDA_PADRAO))
    ap.add_argument("--consultas", default=str(CONSULTAS_PADRAO), help="seed_consultas.csv de entrada")
    ap.add_argument("--saida-consultas", default=str(CONSULTAS_SAIDA_PADRAO), help="seed_consultas ajustado (1 linha por paciente ativo)")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--hoje", type=date.fromisoformat, default=date.today(), help="AAAA-MM-DD (base das idades)")
    ap.add_argument("--sem-validar", action="store_true", help="não valida contra os schemas do projeto")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    pacientes = carregar_pacientes(Path(args.csv), args.hoje)
    casos, seletor = montar_cenarios(pacientes, rng)
    ativos = [p for p in pacientes if p["ativo"]]
    linhas_consulta = completar_consultas(carregar_consultas(Path(args.consultas)), len(ativos), rng)
    consultas, avisos_consulta = atribuir_consultas(casos, ativos, linhas_consulta, rng)
    seletor.avisos.extend(avisos_consulta)
    dados = montar_json(pacientes, casos, consultas, rng, args, seletor.avisos)

    status = 0
    if not args.sem_validar:
        try:
            erros = validar_schemas(dados)
            if erros:
                status = 1
                print(f"{len(erros)} item(ns) INVÁLIDO(s) nos schemas do projeto:")
                for e in erros[:30]:
                    print("  -", e)
            else:
                print("Validação contra os schemas do projeto: OK.")
        except ImportError as e:
            print(f"AVISO: schemas do projeto não importáveis ({e}); validação pulada. "
                  "Rode da raiz do projeto ou use --sem-validar.")

    Path(args.saida).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(args.saida_consultas, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_CONSULTA, lineterminator="\r\n")
        w.writeheader()
        for p in ativos:
            c = consultas[p["linha"]]
            w.writerow({**c, "desfecho_final": c["desfecho_final"] or ""})
    print(f"\n{len(dados['pacientes'])} blocos escritos em {args.saida}")
    for categoria, n in dados["resumo"].items():
        print(f"  {categoria:<26}{n:>4}")
    estados = Counter(consultas[p["linha"]]["cenario"] for p in ativos)
    print(f"\nconsultas -> {args.saida_consultas}")
    for estado, n in sorted(estados.items()):
        print(f"  {estado:<26}{n:>4}")
    for aviso in seletor.avisos:
        print("AVISO:", aviso)
    sys.exit(status)


if __name__ == "__main__":
    main()