def _montar_resumo_clinico(alergias, doencas, medicamentos):
        """NOVO: bloco de alerta no TOPO do prontuário -- pensado para
        ser lido em segundos numa emergência, sem precisar percorrer
        cada array pra saber se há algo grave. Cada resumo é calculado
        aqui (não fica salvo em banco) para nunca divergir dos dados
        reais nas listas completas logo abaixo no mesmo JSON.
        """
        alergias_graves = [a.substancia for a in alergias if a.gravidade == "grave"]
        return {
            "alergias": {
                "total": len(alergias),
                "tem_grave": bool(alergias_graves),
                "resumo": [f"{a.substancia} ({a.gravidade or 'sem reação registrada'})" for a in alergias],
            },
            "doencas_cronicas": {
                "total": len(doencas),
                "ativas": sum(1 for d in doencas if d.status == "ativa"),
                "resumo": [d.descricao_cid10 for d in doencas if d.status == "ativa"],
            },
            "medicamentos_em_uso": {
                "total": len(medicamentos),
                "em_uso_continuo": sum(1 for m in medicamentos if m.status_uso == "ativo"),
                "resumo": [m.descricao for m in medicamentos if m.status_uso == "ativo"],
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
        - Tipo sanguíneo: só o valor atual (via Paciente.tipo_sanguineo,
          já incluído em to_dict()). Histórico completo de observações
          fica de fora, exposto em endpoint separado.
        - resumo_clinico: bloco no topo do dict com contagens e alertas
          de alergia grave, doença crônica ativa e medicamento em uso
          contínuo -- pensado para leitura rápida (emergência), sem
          precisar percorrer os arrays completos logo abaixo.

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
        from .consentimento_service import ConsentimentoService
        from .paciente_service import PacienteService
        
        paciente_svc = PacienteService()
        paciente =paciente_svc.buscar_por_uuid(uuid, id_empresa) 


        alergia_svc = AlergiaService()
        doenca_svc = DoencaCronicaService()
        medicamento_svc = MedicamentoEmUsoService()
        consentimento_svc = ConsentimentoService()

        alergias = alergia_svc.listar_alergias(uuid, id_empresa)
        doencas = doenca_svc.listar_doencas(uuid, id_empresa)
        medicamentos = medicamento_svc.listar_medicamentos_em_uso(uuid, id_empresa)
        consentimento_ativo = consentimento_svc.repo.find_ativo_por_paciente(paciente.id) is not None

        # ALTERADO: alergias ordenadas por gravidade (grave primeiro),
        # não por ordem de cadastro -- uma alergia grave cadastrada há
        # anos não deveria aparecer depois de uma leve cadastrada ontem.
        ordem_gravidade = {"grave": 0, "moderada": 1, "leve": 2, None: 3}
        alergias_ordenadas = sorted(alergias, key=lambda a: ordem_gravidade.get(a.gravidade, 3))

        d = paciente.to_dict()
        d["resumo_clinico"] = paciente._montar_resumo_clinico(alergias, doencas, medicamentos)
        d["alergias"] = [a.to_dict() for a in alergias_ordenadas]
        d["doencas_cronicas"] = [doenca.to_dict() for doenca in doencas]
        d["medicamentos_em_uso"] = [m.to_dict() for m in medicamentos]
        d["consentimento_ativo"] = consentimento_ativo
        return d


        
# Exemplo do json resumo clinico        
# {
#   "success": true,
#   "message": null,
#   "data": {
#     "uuid": "8f14e45f-ceea-4e2a-a11e-1a2b3c4d5e6f",
#     "sexo_biologico": "F",
#     "tipo_sanguineo": "O+",
#     "data_nascimento": "1990-04-12",
#     "status": "ativo",
#     "data_primeiro_atendimento": "2024-01-15",
#     "cadastrado_por": "Ana Beatriz Souza",
#     "criado_em": "2024-01-15T14:32:00+00:00",

#     "resumo_clinico": {
#       "alergias": {
#         "total": 2,
#         "tem_grave": true,
#         "resumo": ["Penicilina (grave)", "Dipirona (moderada)"]
#       },
#       "doencas_cronicas": {
#         "total": 1,
#         "ativas": 1,
#         "resumo": ["Hipertensão essencial"]
#       },
#       "medicamentos_em_uso": {
#         "total": 1,
#         "em_uso_continuo": 1,
#         "resumo": ["Losartana 50mg"]
#       }
#     },

#     "alergias": [
#       {
#         "uuid": "p1p2p3p4-0002-4a1a-9b1b-999999999999",
#         "substancia": "Penicilina",
#         "tipo_reacao": "anafilaxia",
#         "gravidade": "grave",
#         "descricao_reacao": "Reação anafilática, necessitou epinefrina",
#         "flag_confirmado": true,
#         "reacoes": [
#           {
#             "uuid": "r9r8r7r6-0002-4a1a-9b1b-101010101010",
#             "manifestacao": "anafilaxia",
#             "gravidade": "grave",
#             "descricao": "Reação anafilática, necessitou epinefrina",
#             "data_ocorrencia": "2022-03-15"
#           }
#         ]
#       },
#       {
#         "uuid": "a1b2c3d4-0001-4a1a-9b1b-111111111111",
#         "substancia": "Dipirona",
#         "tipo_reacao": "cutanea",
#         "gravidade": "moderada",
#         "descricao_reacao": "Surgiu cerca de 30min após administração",
#         "flag_confirmado": true,
#         "reacoes": [
#           {
#             "uuid": "r1r2r3r4-0001-4a1a-9b1b-222222222222",
#             "manifestacao": "cutanea",
#             "gravidade": "moderada",
#             "descricao": "Surgiu cerca de 30min após administração",
#             "data_ocorrencia": "2023-11-02"
#           }
#         ]
#       }
#     ],

#     "doencas_cronicas": [
#       {
#         "uuid": "d1d2d3d4-0001-4a1a-9b1b-333333333333",
#         "codigo_cid10": "I10",
#         "descricao_cid10": "Hipertensão essencial",
#         "desde": "2019-06-01",
#         "status": "ativa",
#         "observacoes": "Controlada com medicação"
#       }
#     ],

#     "medicamentos_em_uso": [
#       {
#         "uuid": "m1m2m3m4-0001-4a1a-9b1b-444444444444",
#         "descricao": "Losartana 50mg",
#         "dose": "1 comprimido",
#         "frequencia": "1x ao dia",
#         "desde": "2019-06-10",
#         "flag_em_uso": true,
#         "status_uso": "ativo"
#       }
#     ],

#     "consentimento_ativo": true
#   }
# }