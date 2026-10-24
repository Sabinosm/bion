"""paciente_resumo_service.py -- bloco `paciente` das respostas de Consulta e Atendimento.

Monta o resumo do paciente (uuid, nome descriptografado e flags de identificação) a partir
de um Paciente já carregado, sem acessar o banco. O nome é PII: só use em rota de
médico/enfermeiro e, de preferência, com `paciente` e `paciente.pessoal` carregados junto
da query (eager loading) para não gerar uma query por item de lista.
"""

from src.core.security import aes_decrypt


def bloco_paciente(paciente) -> dict:
    """Resumo do paciente para listas e detalhes.

    `nao_identificado`: paciente de emergência ainda sem cadastro.
    `anonimizado`: dados pessoais removidos (LGPD) em paciente que era identificado.
    Com `paciente` None, devolve o bloco com todos os campos vazios/falsos.
    """
    pessoal = paciente.pessoal if paciente else None
    return {
        "uuid": paciente.uuid if paciente else None,
        "nome": aes_decrypt(pessoal.nome_completo) if pessoal else None,
        "nao_identificado": bool(paciente and paciente.nao_identificado),
        "anonimizado": bool(paciente and not pessoal and not paciente.nao_identificado),
    }