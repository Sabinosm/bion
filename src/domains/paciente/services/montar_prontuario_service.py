"""montar_prontuario_service.py

Montagem do prontuário clínico completo de um paciente, usado SÓ na tela de
detalhe (nunca em listagem: cada domínio é uma query própria, custo alto demais
para repetir por paciente numa lista).

O prontuário é o paciente mais os domínios clínicos: tipo sanguíneo vigente,
alergias (grave primeiro), doenças crônicas vigentes, medicamentos em uso (ativos
primeiro, encerrados como histórico) e as interações entre os medicamentos
ativos. No topo vai o resumo clínico (tipo sanguíneo, contagens e alertas de
alergia grave, doença ativa e medicamento em uso), calculado na hora a partir das
mesmas listas, para leitura rápida em emergência e sem divergir dos dados.

Decisões: o consentimento fica FORA do agregado (é titularidade/LGPD, não dado
clínico) e entra só como o booleano `consentimento_ativo`; o tipo sanguíneo é só o
VIGENTE (o histórico tem endpoint próprio); o histórico de revisões das doenças
também fica de fora. Os imports dos services são locais ao método para evitar
dependência circular com o pacote de services e para não carregar todos os
services toda vez que o PacienteService é instanciado.
"""

_ORDEM_GRAVIDADE = {"grave": 0, "moderada": 1, "leve": 2, None: 3}


def _montar_resumo_clinico(alergias, doencas, medicamentos, tipo_obs=None):
    """Bloco de alerta do topo do prontuário.

    `tipo_obs` é a observação VIGENTE de tipo sanguíneo (None se nunca registrado). As listas já
    chegam filtradas pelos services: doenças só vigentes (nem removidas nem encerradas por
    revisão); medicamentos todos os não removidos (ativos e encerrados), sendo "ativo" a
    propriedade MedicamentoEmUso.ativo.
    """
    alergias_graves = [a.substancia for a in alergias if a.gravidade_maxima == "grave"]
    return {
        "tipo_sanguineo": {
            # Três estados distintos:
            #   registrado=False                  -> nunca coletado
            #   registrado=True, conhecido=False  -> registrado como "desconhecido"
            #   conhecido=True                    -> tem valor
            "registrado": tipo_obs is not None,
            "valor": tipo_obs.tipo_sanguineo if tipo_obs else None,
            "conhecido": tipo_obs is not None and tipo_obs.tipo_sanguineo != "desconhecido",
            "registrado_em": (tipo_obs.data_registro.isoformat()
                              if tipo_obs and tipo_obs.data_registro else None),
        },
        "alergias": {
            "total": len(alergias),
            "tem_grave": bool(alergias_graves),
            "resumo": [f"{a.substancia} ({a.gravidade_maxima or 'sem reação registrada'})" for a in alergias],
        },
        "doencas_cronicas": {
            "total": len(doencas),
            "ativas": sum(1 for d in doencas if d.status == "ativa"),
            "resumo": [d.descricao_cid10 for d in doencas if d.status == "ativa"],
        },
        "medicamentos_em_uso": {
            "total": len(medicamentos),
            "em_uso_continuo": sum(1 for m in medicamentos if m.ativo),
            "resumo": [m.descricao for m in medicamentos if m.ativo],
            # Ativos SEM vínculo com o catálogo não entram na checagem de interações: o leitor
            # precisa saber que há medicamento que o sistema não consegue cruzar.
            "nao_verificaveis_interacao": sum(
                1 for m in medicamentos if m.ativo and m.id_catalogo is None
            ),
        },
    }


def montar_prontuario_completo(uuid: str, id_empresa: int):
    """Dict do paciente com os domínios clínicos agregados (ver o docstring do módulo).

    Campos acrescentados ao `to_dict()` do paciente: `tipo_sanguineo` (string, vigente),
    `tipo_sanguineo_vigente` (observação completa), `resumo_clinico`, `alergias`,
    `doencas_cronicas`, `medicamentos_em_uso`, `interacoes_medicamentosas` (com `cobertura`: lista
    vazia não prova ausência de interação) e `consentimento_ativo`.

    Raises:
        RecursoNaoEncontradoError: paciente inexistente na empresa.
    """
    from .alergia_service import AlergiaService
    from .doenca_cronica_service import DoencaCronicaService
    from .medicamento_em_uso_service import MedicamentoEmUsoService
    from .obs_tipo_sanguineo_service import ObservacaoTipoSanguineoService
    from .consentimento_service import ConsentimentoService
    from .paciente_service import PacienteService

    paciente = PacienteService().buscar_por_uuid(uuid, id_empresa)

    medicamento_svc = MedicamentoEmUsoService()
    alergias = AlergiaService().listar_alergias(uuid, id_empresa)
    doencas = DoencaCronicaService().listar_doencas(uuid, id_empresa)
    medicamentos = medicamento_svc.listar_medicamentos_em_uso(uuid, id_empresa)
    interacoes = medicamento_svc.verificar_interacoes_do_paciente(uuid, id_empresa)
    tipo_obs = ObservacaoTipoSanguineoService().tipo_vigente(uuid, id_empresa)  # None se nunca registrado
    consentimento_ativo = ConsentimentoService().repo.find_ativo_por_paciente(paciente.id) is not None

    # Alergia grave primeiro, não por ordem de cadastro: uma alergia grave cadastrada há anos não
    # deve aparecer depois de uma leve cadastrada ontem.
    alergias_ordenadas = sorted(alergias, key=lambda a: _ORDEM_GRAVIDADE.get(a.gravidade_maxima, 3))

    d = paciente.to_dict()
    d["tipo_sanguineo"] = tipo_obs.tipo_sanguineo if tipo_obs else None
    d["tipo_sanguineo_vigente"] = tipo_obs.to_dict() if tipo_obs else None
    d["resumo_clinico"] = _montar_resumo_clinico(alergias, doencas, medicamentos, tipo_obs)
    d["resumo_clinico"]["medicamentos_em_uso"]["interacoes_encontradas"] = len(interacoes["interacoes"])
    d["alergias"] = [a.to_dict() for a in alergias_ordenadas]
    d["doencas_cronicas"] = [doenca.to_dict() for doenca in doencas]
    d["medicamentos_em_uso"] = [m.to_dict() for m in medicamentos]
    d["interacoes_medicamentosas"] = interacoes
    d["consentimento_ativo"] = consentimento_ativo
    return d
