"""
Testes unitarios do motor de protocolos (Strategy/Factory).

Cobrem especificamente os 3 pontos que quebravam em runtime no
bion.zip original (ver docstrings de correcao em src/domains/
protocolos_ia/motor/base.py, mts.py e news2.py).
"""

import pytest

from src.domains.protocolos_ia.motor.base import InputTriagem, InputConsulta
from src.domains.protocolos_ia.motor.mts import MtsProtocolo
from src.domains.protocolos_ia.motor.news2 import News2Protocolo
from src.domains.protocolos_ia.motor.personalizado import ProtocoloPersonalizado
from src.domains.protocolos_ia.motor.factory import ProtocoloFactory


class DummyCatalogo:
    def __init__(self, sigla):
        self.sigla = sigla


def test_mts_executa_e_retorna_cor_correta():
    """Regressão do bug: ResultadoTriagem sem discriminadores_avaliados/
    discriminante_determinante quebrava com TypeError."""
    motor = MtsProtocolo()
    inp = InputTriagem(input_json={
        "fluxograma": {"discriminadores": [
            {"nome": "dor toracica", "resultado": "positivo", "cor_resultante": "Laranja"},
        ]}
    })
    resultado = motor.executar(inp)
    assert resultado.cor_mts == "Laranja"
    assert resultado.tempo_max_espera == 10
    assert resultado.discriminante_determinante == "dor toracica"


def test_mts_sem_discriminador_positivo_retorna_verde():
    motor = MtsProtocolo()
    inp = InputTriagem(input_json={"fluxograma": {"discriminadores": []}})
    resultado = motor.executar(inp)
    assert resultado.cor_mts == "Verde"
    assert resultado.tempo_max_espera == 120


def test_mts_validar_input_usa_queixa_principal():
    """Regressão do bug: validar_input acessava i.queixa_principal, atributo
    que não existia no dataclass original."""
    motor = MtsProtocolo()
    assert motor.validar_input(InputTriagem(queixa_principal="dor no peito")) is True
    assert motor.validar_input(InputTriagem()) is False


def test_news2_calcula_score_e_nivel_risco():
    """Regressão do bug: ResultadoTriagem não tinha nivel_risco_news2/
    score_news2/subscores_news2, e InputTriagem não tinha sinais_vitais."""
    motor = News2Protocolo()
    inp = InputTriagem(sinais_vitais=[
        {"tipo_parametro": "frequencia-respiratoria", "valor_numerico": 22},
        {"tipo_parametro": "spo2", "valor_numerico": 94},
    ])
    resultado = motor.executar(inp)
    assert resultado.score_news2 == 3
    assert resultado.nivel_risco_news2 == "baixo"


def test_news2_score_alto_gera_alerta():
    motor = News2Protocolo()
    inp = InputTriagem(sinais_vitais=[
        {"tipo_parametro": "frequencia-respiratoria", "valor_numerico": 3},  # pontuação 3 = crítico
    ])
    resultado = motor.executar(inp)
    assert resultado.nivel_risco_news2 == "alto"
    assert len(resultado.alertas) == 1


def test_news2_funciona_tambem_como_protocolo_de_consulta():
    motor = News2Protocolo()
    inp = InputConsulta(sinais_vitais=[
        {"tipo_parametro": "spo2", "valor_numerico": 99},
    ])
    resultado = motor.executar(inp)
    assert 0.0 <= resultado.indice_confianca <= 1.0


def test_protocolo_personalizado_extrai_alertas_das_regras_disparadas():
    motor = ProtocoloPersonalizado()
    inp = InputConsulta(input_json={"regras_avaliadas": [
        {"disparada": True, "acao": "encaminhar cardiologia"},
        {"disparada": False, "acao": "nao deve aparecer"},
    ]})
    resultado = motor.executar(inp)
    assert resultado.alertas == ["encaminhar cardiologia"]


@pytest.mark.parametrize("sigla,classe_esperada", [
    ("MTS", MtsProtocolo),
    ("NEWS2", News2Protocolo),
    ("PP", ProtocoloPersonalizado),
])
def test_factory_cria_motor_correto_por_sigla(sigla, classe_esperada):
    motor = ProtocoloFactory().criar(DummyCatalogo(sigla))
    assert isinstance(motor, classe_esperada)


def test_factory_sigla_desconhecida_leva_a_erro():
    with pytest.raises(ValueError):
        ProtocoloFactory().criar(DummyCatalogo("SIGLA_INEXISTENTE"))
