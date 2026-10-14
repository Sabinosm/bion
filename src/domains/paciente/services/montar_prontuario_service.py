def _montar_resumo_clinico(alergias, doencas, medicamentos, tipo_obs=None):
        """NOVO: bloco de alerta no TOPO do prontuário -- pensado para
        ser lido em segundos numa emergência, sem precisar percorrer
        cada array pra saber se há algo grave. Cada resumo é calculado
        aqui (não fica salvo em banco) para nunca divergir dos dados
        reais nas listas completas logo abaixo no mesmo JSON.

        tipo_obs: observação VIGENTE de tipo sanguíneo (ou None se nunca
        registrado), vinda de TipoSanguineoService.tipo_vigente.
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
                # doencas já vem de DoencaCronicaService.listar_doencas:
                # só VIGENTES (não removidas e não encerradas por revisão).
                # total = ativa + em-remissao vigentes; linhas antigas de
                # uma doença revisada ficam no histórico, fora daqui.
                "total": len(doencas),
                "ativas": sum(1 for d in doencas if d.status == "ativa"),
                "resumo": [d.descricao_cid10 for d in doencas if d.status == "ativa"],
            },
            "medicamentos_em_uso": {
                # medicamentos já vem filtrado (deletado=False) por
                # MedicamentoEmUsoService.listar_medicamentos_em_uso --
                # total aqui é "não removidos" (ativos + encerrados, que
                # ficam como histórico). "Ativo" = status_uso='ativo' e
                # não deletado (propriedade MedicamentoEmUso.ativo);
                # flag_em_uso não existe mais.
                "total": len(medicamentos),
                "em_uso_continuo": sum(1 for m in medicamentos if m.ativo),
                "resumo": [m.descricao for m in medicamentos if m.ativo],
                # Ativos SEM vínculo com o catálogo não entram na
                # checagem de interações -- o leitor precisa saber que
                # há medicamento que o sistema não consegue cruzar.
                "nao_verificaveis_interacao": sum(
                    1 for m in medicamentos if m.ativo and m.id_catalogo is None
                ),
            },
        }

def montar_prontuario_completo(uuid: str, id_empresa: int):
        """NOVO: agrega o paciente + todos os domínios clínicos num
        único dict -- usado SÓ na tela de detalhe (nunca em listagem;
        cada domínio aqui é uma query própria, custo alto demais para
        repetir por paciente numa lista).

        Decisões confirmadas:
        - Consentimento fica FORA do agregado -- é sobre titularidade/
          LGPD, não é dado clínico. Só entra como um booleano
          (consentimento_ativo), não a lista de termos/histórico --
          quem quiser o histórico completo usa a rota própria do
          LgpdController.
        - Tipo sanguíneo: só o VIGENTE (observação mais recente), lido
          por TipoSanguineoService.tipo_vigente -- uma query, sem
          carregar o histórico. Entra em três lugares, todos da mesma
          fonte: `tipo_sanguineo` (string, compatível com o front atual),
          `tipo_sanguineo_vigente` (observação completa: quem, quando,
          atendimento de origem) e resumo_clinico.tipo_sanguineo. O
          histórico completo fica de fora, em
          GET /<uuid_paciente>/tipo-sanguineo/historico.
        - doencas_cronicas: só as doenças VIGENTES (listar_doencas). O
          histórico de revisões (status/CID/desde que mudaram ao longo
          dos atendimentos) fica de fora, exposto em
          GET /<uuid_paciente>/doencas-cronicas/historico.
        - medicamentos_em_uso: lista TODOS os não removidos (ativos
          primeiro, encerrados como histórico); cada item traz `ativo`,
          `ate`, `catalogo` e `uuid_atendimento_origem`.
        - interacoes_medicamentosas: interações cadastradas ENTRE os
          medicamentos ativos (mesmo resultado de GET
          /<uuid_paciente>/medicamentos-em-uso/interacoes), com
          `nao_verificados` e `cobertura`. Lista vazia não prova ausência
          de interação -- ver `cobertura.aviso`. Custo: algumas queries a
          mais, aceitável por ser tela de detalhe.
        - resumo_clinico: bloco no topo do dict com tipo sanguíneo e
          contagens e alertas de alergia grave, doença crônica ativa e
          medicamento em uso contínuo -- pensado para leitura rápida
          (emergência), sem precisar percorrer os arrays completos logo
          abaixo.

        Import direto dos módulos (não via
        src.domains.paciente.services, o __init__.py agregador) --
        este arquivo já é um dos módulos importados por aquele
        __init__.py, então importar de volta o pacote inteiro criaria
        dependência circular. Import local (dentro do método, não no
        topo do arquivo) continua necessário para não carregar todos
        os services de domínio toda vez que PacienteService for
        instanciado, quando a maioria das chamadas nem usa o agregador.
        """
        from .alergia_service import AlergiaService
        from .doenca_cronica_service import DoencaCronicaService
        from .medicamento_em_uso_service import MedicamentoEmUsoService
        from .obs_tipo_sanguineo_service import ObservacaoTipoSanguineoService
        from .consentimento_service import ConsentimentoService
        from .paciente_service import PacienteService

        paciente_svc = PacienteService()
        paciente = paciente_svc.buscar_por_uuid(uuid, id_empresa)

        alergia_svc = AlergiaService()
        doenca_svc = DoencaCronicaService()
        medicamento_svc = MedicamentoEmUsoService()
        tipo_svc = ObservacaoTipoSanguineoService()
        consentimento_svc = ConsentimentoService()

        alergias = alergia_svc.listar_alergias(uuid, id_empresa)
        doencas = doenca_svc.listar_doencas(uuid, id_empresa)
        medicamentos = medicamento_svc.listar_medicamentos_em_uso(uuid, id_empresa)
        interacoes = medicamento_svc.verificar_interacoes_do_paciente(uuid, id_empresa)
        tipo_obs = tipo_svc.tipo_vigente(uuid, id_empresa)   # None se nunca registrado
        consentimento_ativo = consentimento_svc.repo.find_ativo_por_paciente(paciente.id) is not None

        # ALTERADO: alergias ordenadas por gravidade (grave primeiro),
        # não por ordem de cadastro -- uma alergia grave cadastrada há
        # anos não deveria aparecer depois de uma leve cadastrada ontem.
        ordem_gravidade = {"grave": 0, "moderada": 1, "leve": 2, None: 3}
        alergias_ordenadas = sorted(alergias, key=lambda a: ordem_gravidade.get(a.gravidade_maxima, 3))

        d = paciente.to_dict()
        # ALTERADO: tipo sanguíneo vem do vigente lido acima (mesma fonte
        # do resumo), não mais de Paciente.tipo_sanguineo.
        d["tipo_sanguineo"] = tipo_obs.tipo_sanguineo if tipo_obs else None
        d["tipo_sanguineo_vigente"] = tipo_obs.to_dict() if tipo_obs else None
        d["resumo_clinico"] = _montar_resumo_clinico(alergias, doencas, medicamentos, tipo_obs)
        # contagem de leitura rápida, calculada a partir do mesmo
        # resultado que vai em d["interacoes_medicamentosas"]
        d["resumo_clinico"]["medicamentos_em_uso"]["interacoes_encontradas"] = len(
            interacoes["interacoes"]
        )
        d["alergias"] = [a.to_dict() for a in alergias_ordenadas]
        d["doencas_cronicas"] = [doenca.to_dict() for doenca in doencas]
        d["medicamentos_em_uso"] = [m.to_dict() for m in medicamentos]
        d["interacoes_medicamentosas"] = interacoes
        d["consentimento_ativo"] = consentimento_ativo
        return d


    # Exemplo do json (campos de tipo sanguíneo; o resto segue como antes)
    # {
    #   "success": true,
    #   "message": null,
    #   "data": {
    #     "uuid": "8f14e45f-ceea-4e2a-a11e-1a2b3c4d5e6f",
    #     "sexo_biologico": "F",
    #     "tipo_sanguineo": "O+",
    #     "tipo_sanguineo_vigente": {
    #       "uuid": "t1t2t3t4-0001-4a1a-9b1b-777777777777",
    #       "tipo_sanguineo": "O+",
    #       "data_registro": "2024-01-15T14:40:00+00:00",
    #       "registrado_por": "Ana Beatriz Souza",
    #       "atendimento_origem_uuid": "a7a6a5a4-0003-4a1a-9b1b-555555555555"
    #     },
    #     "resumo_clinico": {
    #       "tipo_sanguineo": {
    #         "registrado": true,
    #         "valor": "O+",
    #         "conhecido": true,
    #         "registrado_em": "2024-01-15T14:40:00+00:00"
    #       },
    #       "alergias": { "total": 2, "tem_grave": true, "resumo": ["Penicilina (grave)", "Dipirona (moderada)"] },
    #       "doencas_cronicas": { "total": 1, "ativas": 1, "resumo": ["Hipertensão essencial"] },
    #       "medicamentos_em_uso": { "total": 1, "em_uso_continuo": 1, "resumo": ["Losartana 50mg"],
    #                                "nao_verificaveis_interacao": 0, "interacoes_encontradas": 0 }
    #     },
    #     "alergias": [ ... ],
    #     "doencas_cronicas": [ ... ],
    #     "medicamentos_em_uso": [ ... ],
    #     "interacoes_medicamentosas": { ... },
    #     "consentimento_ativo": true
    #   }
    # }