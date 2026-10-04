"""Seed do protocolo NEWS2 (National Early Warning Score 2, RCP UK) no catálogo.
Roda uma vez, por governança clínica -- nunca é chamado por uma rota da aplicação.
Usa SpO2 Scale 1 (paciente sem insuficiência respiratória hipercápnica crônica);
Scale 2 fica para uma revisão futura, exigiria campo condicional retentor_co2.
"""

from src.models import db
from src.models.protocolos import ProtocoloCatalogo, ProtocoloVersao, ProtocoloEscoreConfig
from src.domains.protocolo.shared.schemas.schema_explicacao_protocolo import ExplicacaoProtocolo

def seed_news2():
    explicacao = ExplicacaoProtocolo(
        o_que_e="Escore de alerta precoce que agrega sete parâmetros fisiológicos "
                "(frequência respiratória, saturação de O2, uso de oxigênio suplementar, "
                "temperatura, pressão arterial sistólica, frequência cardíaca e nível de "
                "consciência) para identificar deterioração clínica em pacientes adultos.",
        quando_usar="Reavaliação periódica de pacientes internados, ou triagem e "
                    "monitorização em urgência/emergência. Não validado para gestantes "
                    "ou população pediátrica.",
        como_interpretar="A soma dos pontos de cada parâmetro define o risco: 0 é rotina, "
                          "1-4 é baixo risco, 5-6 é médio risco (resposta em até 1h), 7+ é alto "
                          "risco (resposta de emergência). Qualquer parâmetro isolado que pontue "
                          "o máximo (3) já dispara avaliação clínica urgente, independente do total.",
    )

    catalogo = ProtocoloCatalogo(
        nome_protocolo="National Early Warning Score 2",
        sigla="NEWS2",
        tipo_resultado="score-numerico",
        tipo_protocolo="escore-ponderado",
        escopo_populacao="adulto",
        escopo_uso="ambos",
        versao_vigente="2.0",
        data_vigencia="2017-12-01",
        referencia_bibliografica="Royal College of Physicians. National Early Warning Score (NEWS) 2: "
                                  "Standardising the assessment of acute-illness severity in the NHS. "
                                  "Updated report of a working party. London: RCP, 2017.",
        orgao_emissor="Royal College of Physicians (RCP UK)",
        status="ativo",
        explicacao_json=explicacao.model_dump(),
    )
    db.session.add(catalogo)
    db.session.flush()

    versao = ProtocoloVersao(
        id_protocolo_catalogo=catalogo.id,
        numero_versao="2.0",
        vigente_desde="2017-12-01",
        status="ativa",
        observacoes="SpO2 Scale 1 apenas. Scale 2 (retentores de CO2) não implementada nesta versão.",
    )
    db.session.add(versao)

    parametros = [
        {
            "campo": "frequencia_respiratoria",
            "rotulo": "Frequência respiratória",
            "unidade": "irpm",
            "tipo_campo": "numero",
            "faixas": [
                {"valor_min": None, "valor_max": 8, "pontos": 3},
                {"valor_min": 9, "valor_max": 11, "pontos": 1},
                {"valor_min": 12, "valor_max": 20, "pontos": 0},
                {"valor_min": 21, "valor_max": 24, "pontos": 2},
                {"valor_min": 25, "valor_max": None, "pontos": 3},
            ],
        },
        {
            "campo": "spo2",
            "rotulo": "Saturação de O2 (Scale 1)",
            "unidade": "%",
            "tipo_campo": "numero",
            "faixas": [
                {"valor_min": None, "valor_max": 91, "pontos": 3},
                {"valor_min": 92, "valor_max": 93, "pontos": 2},
                {"valor_min": 94, "valor_max": 95, "pontos": 1},
                {"valor_min": 96, "valor_max": None, "pontos": 0},
            ],
        },
        {
            "campo": "uso_oxigenio_suplementar",
            "rotulo": "Em uso de oxigênio suplementar?",
            "unidade": None,
            "tipo_campo": "enum",
            "opcoes": [
                {"valor": "nao", "rotulo": "Ar ambiente", "pontos": 0},
                {"valor": "sim", "rotulo": "Oxigênio suplementar", "pontos": 2},
            ],
        },
        {
            "campo": "temperatura",
            "rotulo": "Temperatura",
            "unidade": "°C",
            "tipo_campo": "numero",
            # Intervalos semiabertos [min, max): min <= x < max, sem lacunas decimais.
            "intervalo": "min_inclusivo_max_exclusivo",
            "faixas": [
                {"valor_min": None, "valor_max": 35.1, "pontos": 3},
                {"valor_min": 35.1, "valor_max": 36.1, "pontos": 1},
                {"valor_min": 36.1, "valor_max": 38.1, "pontos": 0},
                {"valor_min": 38.1, "valor_max": 39.1, "pontos": 1},
                {"valor_min": 39.1, "valor_max": None, "pontos": 2},
            ],
        },
        {
            "campo": "pressao_arterial_sistolica",
            "rotulo": "Pressão arterial sistólica",
            "unidade": "mmHg",
            "tipo_campo": "numero",
            "faixas": [
                {"valor_min": None, "valor_max": 90, "pontos": 3},
                {"valor_min": 91, "valor_max": 100, "pontos": 2},
                {"valor_min": 101, "valor_max": 110, "pontos": 1},
                {"valor_min": 111, "valor_max": 219, "pontos": 0},
                {"valor_min": 220, "valor_max": None, "pontos": 3},
            ],
        },
        {
            "campo": "frequencia_cardiaca",
            "rotulo": "Frequência cardíaca",
            "unidade": "bpm",
            "tipo_campo": "numero",
            "faixas": [
                {"valor_min": None, "valor_max": 40, "pontos": 3},
                {"valor_min": 41, "valor_max": 50, "pontos": 1},
                {"valor_min": 51, "valor_max": 90, "pontos": 0},
                {"valor_min": 91, "valor_max": 110, "pontos": 1},
                {"valor_min": 111, "valor_max": 130, "pontos": 2},
                {"valor_min": 131, "valor_max": None, "pontos": 3},
            ],
        },
        {
            "campo": "nivel_consciencia",
            "rotulo": "Nível de consciência (ACVPU)",
            "unidade": None,
            "tipo_campo": "enum",
            "opcoes": [
                {"valor": "alerta", "rotulo": "Alerta", "pontos": 0},
                {"valor": "confusao_nova", "rotulo": "Confuso (nova alteração)", "pontos": 3},
                {"valor": "voz", "rotulo": "Responde à voz (V)", "pontos": 3},
                {"valor": "dor", "rotulo": "Responde à dor (P)", "pontos": 3},
                {"valor": "irresponsivo", "rotulo": "Irresponsivo (U)", "pontos": 3},
            ],
        },
    ]

    faixas_interpretacao = [
        {"total_min": 0, "total_max": 0, "categoria": "baixo", "acao_recomendada": "Monitorização de rotina (mínimo 12/12h)."},
        {"total_min": 1, "total_max": 4, "categoria": "baixo", "acao_recomendada": "Avaliação por enfermeiro; considerar aumento da frequência de monitorização."},
        {"total_min": 5, "total_max": 6, "categoria": "medio", "acao_recomendada": "Resposta urgente: avaliação médica em até 1h."},
        {"total_min": 7, "total_max": 20, "categoria": "alto", "acao_recomendada": "Resposta de emergência: avaliação médica imediata, considerar UTI/cuidados críticos."},
    ]

    # Colunas db.JSON: passar objetos Python direto (sem json.dumps).
    config = ProtocoloEscoreConfig(
        id_protocolo_catalogo=catalogo.id,
        parametros_json=parametros,
        regra_override_json={
            "condicao": "qualquer_parametro_score_3",
            "acao": "avaliacao_clinica_urgente",
            "descricao": "Avaliação urgente por clínico, mesmo com total 0-4.",
        },
        faixas_interpretacao_json=faixas_interpretacao,
        schema_version="1.1",
        status="ativo",
    )
    db.session.add(config)

    db.session.commit()
    print("ok")
    return catalogo

if __name__ == "__main__":
    from src.main import create_app

    app = create_app()
    
    with app.app_context():
        seed_news2()
        print("Seed do NEWS2 concluído.")