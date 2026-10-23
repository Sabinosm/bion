"""service_atualizar.py -- atualização parcial de cadastro de usuário.

Implementa o fluxo de edição de um usuário existente em etapas:
checa permissões, valida separadamente os dois eixos independentes
(cargo de admin e função clínica), garante que o usuário resultante
continue com algum acesso, valida o payload parcial, confere
duplicidade, mescla o payload com os dados atuais, revalida como cadastro
completo e persiste, mantendo o histórico dos papéis profissionais
trocados. Fica separado do service principal só para não inflá-lo; a
função daqui recebe o próprio service como primeiro argumento.
"""

from pydantic import ValidationError

from src.core.security import aes_encrypt, hmac_sha256, aes_decrypt
from src.core.exceptions import DadosInvalidosError
from src.core.erros_pydantic import erros_pydantic_por_campo
from .service_helpers import (
    CAMPOS_SIMPLES_ATUALIZAVEIS,
    atributos_atuais,
    monta_dados_papel,
)
from src.domains.usuario.schema_usuario import CadastroUsuarioSchema, AtualizacaoUsuarioSchema
from src.models.usuarios.papel_profissional import PapelProfissional

CAMPOS_DADOS_PROFISSIONAIS = (
    "numero_crm", "uf_crm", "rqe", "numero_coren", "uf_coren", "especialidade",
)


def att(
    svc,
    uuid: str,
    dados: dict,
    solicitante_is_admin: bool,
    solicitante_uuid: str,
    id_empresa_solicitante: int,
    solicitante_eh_super_admin: bool = False,
):
    """Atualiza parcialmente os dados de um usuário existente.

    Regras:
      - is_admin nunca muda por edição de cadastro (nem promover, nem
        rebaixar), para qualquer solicitante, inclusive o super admin.
        Virar admin só acontece na criação.
      - tipo_papel (função clínica) pode ser trocado; o papel antigo é
        desativado, não apagado, para preservar histórico.
      - O usuário resultante nunca pode ficar sem ser admin e sem função
        clínica. Isso depende do estado atual mesclado ao payload, por
        isso é checado aqui e não no schema. A checagem também dispara em
        edições que não tocam esses campos se o usuário já estiver
        inconsistente por dado legado (bloqueia até corrigir).

    Parâmetros:
        svc: instância de UsuarioService (fornece repo, buscar_por_uuid_da_empresa e
            as validações); não é o model Usuario.
        uuid: identificador do usuário a atualizar.
        dados: payload parcial, com as chaves no formato da API
            (ex.: "numero-crm").
        solicitante_is_admin: se o solicitante é admin.
        solicitante_uuid: UUID do solicitante (hoje não influencia
            nenhuma regra).
        id_empresa_solicitante: empresa do solicitante; o alvo precisa
            pertencer a ela.
        solicitante_eh_super_admin: se o solicitante é o administrador
            principal (necessário para alterar outro admin).

    Retorno:
        Instância de Usuario atualizada e salva.

    Levanta:
        RecursoNaoEncontradoError: se o usuário não existir ou for de
            outra empresa.
        DadosInvalidosError: violação de permissão ou de validação,
            tentativa de mexer em is_admin, usuário resultante sem admin
            e sem papel, ou schema inválido.
        ConflictoError: se CPF, e-mail ou login já pertencerem a outro
            usuário.
    """
    u = svc.buscar_por_uuid_da_empresa(uuid, id_empresa_solicitante)

    svc._valida_permissao_edicao(
        dados, solicitante_is_admin, solicitante_eh_super_admin, u
    )

    atributos_atuais_u = atributos_atuais(u)  # no formato do payload (numero-crm etc)

    is_admin_atual = u.is_admin
    novo_is_admin = dados.get("is_admin", is_admin_atual)
    admin_mudou = novo_is_admin != is_admin_atual

    papel_atual_tipo = u.funcao_clinica
    novo_papel_tipo = dados.get("tipo_papel", papel_atual_tipo)
    papel_mudou = novo_papel_tipo != papel_atual_tipo

    svc._valida_alteracao_admin(admin_mudou)
    svc._valida_troca_tipo(papel_atual_tipo, novo_papel_tipo, papel_mudou, dados)

    if not novo_is_admin and novo_papel_tipo is None:
        raise DadosInvalidosError(
            "O usuário resultante ficaria sem ser administrador e sem "
            "função clínica. Defina 'is_admin' ou 'tipo_papel'."
        )

    try:
        schema_parcial = AtualizacaoUsuarioSchema(**dados)
    except ValidationError as e:
        raise DadosInvalidosError(erros_pydantic_por_campo(e))

    campos_enviados = schema_parcial.model_dump(exclude_unset=True, exclude_none=True)
    if not campos_enviados:
        raise DadosInvalidosError("Nenhum campo para atualizar foi enviado.")

    cpf_novo = campos_enviados.get("cpf")
    email_novo = campos_enviados.get("email")
    login_novo = campos_enviados.get("user_login")

    cpf_hash_novo = hmac_sha256(cpf_novo) if cpf_novo else None
    cpf_mudou = bool(cpf_hash_novo) and cpf_hash_novo != u.cpf_hash

    svc._checar_duplicidade(
        cpf_hash=cpf_hash_novo if cpf_mudou else None,
        email=email_novo if email_novo and email_novo != u.email else None,
        login=login_novo if login_novo and login_novo != u.user_login else None,
        ignorar_uuid=uuid,
    )

    # Revalida o resultado final (dados atuais + payload) como cadastro completo.
    dados_mesclados = {
        "nome_completo": u.nome_completo,
        "cpf": campos_enviados.get("cpf") or aes_decrypt(u.cpf),
        "email": u.email,
        "user_login": u.user_login,
        "is_admin": is_admin_atual,
        "tipo_papel": papel_atual_tipo,
        "telefone": u.telefone,
        "numero-crm": atributos_atuais_u.get("numero-crm"),
        "uf-crm": atributos_atuais_u.get("uf-crm"),
        "rqe": atributos_atuais_u.get("rqe"),
        "numero-coren": atributos_atuais_u.get("numero-coren"),
        "uf-coren": atributos_atuais_u.get("uf-coren"),
        "especialidade": atributos_atuais_u.get("especialidade"),
    }
    dados_mesclados.update(dados)

    try:
        schema_completo = CadastroUsuarioSchema(**dados_mesclados)
    except Exception as e:
        raise DadosInvalidosError(f"Erro de validação: {e}") from e

    for campo in CAMPOS_SIMPLES_ATUALIZAVEIS:
        if campo in campos_enviados:
            setattr(u, campo, getattr(schema_completo, campo))

    if "cpf" in campos_enviados:
        u.cpf = aes_encrypt(schema_completo.cpf)
        u.cpf_hash = hmac_sha256(schema_completo.cpf)

    # Eixo da função clínica (u.is_admin nunca é tocado aqui: já foi
    # barrado por _valida_alteracao_admin).
    campos_papel_mudaram = any(c in campos_enviados for c in CAMPOS_DADOS_PROFISSIONAIS)

    if papel_mudou or campos_papel_mudaram:
        papel_atual = u.papel_ativo()

        if papel_mudou and papel_atual:
            papel_atual.ativo = False  # desativa em vez de apagar: preserva histórico

        dados_papel_novos = monta_dados_papel(schema_completo)

        if dados_papel_novos:
            if papel_mudou or not papel_atual:
                u.papeis.append(PapelProfissional(**dados_papel_novos))
            else:
                # Mesmo tipo: atualiza o papel existente em vez de duplicar.
                for campo, valor in dados_papel_novos.items():
                    setattr(papel_atual, campo, valor)

    return svc.repo.save(u)