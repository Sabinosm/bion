from src.core.security import ph, aes_encrypt, hmac_sha256, aes_decrypt
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from ..repository import UsuarioRepository
from .service_helpers import (
    CAMPOS_SIMPLES_ATUALIZAVEIS,
    CAMPOS_RESTRITOS_A_ADMIN,
    atributos_atuais,
    monta_atributos_json,
)
from .service_reset import ResetCredenciaisMixin
from src.schemas.schema_usuario import CadastroUsuarioSchema, AtualizacaoUsuarioSchema
from src.models.usuarios import Usuario


def att(user: Usuario, uuid: str, dados: dict, solicitante_eh_admin: bool, solicitante_uuid: str):
        """Atualiza parcialmente os dados de um usuário existente.

        Orquestra a atualização em etapas: valida permissão de edição,
        valida troca de tipo profissional (se houver), mescla os dados
        enviados com os atuais, revalida como cadastro completo e persiste.

        Parâmetros:
            uuid: identificador do usuário a atualizar.
            dados: dicionário parcial com os campos a alterar.
            solicitante_eh_admin: se True, o solicitante pode alterar
                campos restritos.
            solicitante_uuid: UUID de quem está fazendo a requisição,
                usado para detectar auto-edição.

        Retorno:
            Instância de Usuario atualizada e salva.

        Levanta:
            DadosInvalidosError: em qualquer violação das regras de
                validação, campos ausentes ou schema inválido.
            ConflictoError: se o novo CPF, e-mail ou login já existirem.
        """
        u = user.buscar_por_uuid(uuid)
        eh_auto_edicao = (uuid == solicitante_uuid)

        user._valida_permissao_edicao(dados, solicitante_eh_admin, eh_auto_edicao, u)

        atributos_atuais_u = atributos_atuais(u)
        novo_tipo = dados.get("tipo_usuario", u.tipo_usuario)
        tipo_mudou = novo_tipo != u.tipo_usuario

        user._valida_troca_tipo(novo_tipo, tipo_mudou, dados)

        try:
            schema_parcial = AtualizacaoUsuarioSchema(**dados)
        except Exception as e:
            raise DadosInvalidosError(f"Erro de validação: {e}") from e

        campos_enviados = schema_parcial.model_dump(exclude_unset=True, exclude_none=True)
        if not campos_enviados:
            raise DadosInvalidosError("Nenhum campo para atualizar foi enviado.")

        cpf_novo = campos_enviados.get("cpf")
        email_novo = campos_enviados.get("email")
        login_novo = campos_enviados.get("user_login")

        cpf_hash_novo = hmac_sha256(cpf_novo) if cpf_novo else None
        cpf_mudou = bool(cpf_hash_novo) and cpf_hash_novo != u.cpf_hash

        user._checar_duplicidade(
            cpf_hash=cpf_hash_novo if cpf_mudou else None,
            email=email_novo if email_novo and email_novo != u.email else None,
            login=login_novo if login_novo and login_novo != u.user_login else None,
            ignorar_uuid=uuid,
        )

        cpf_para_validar = campos_enviados.get("cpf") or aes_decrypt(u.cpf)

        dados_mesclados = {
            "nome_completo": u.nome_completo,
            "cpf": cpf_para_validar,
            "email": u.email,
            "user_login": u.user_login,
            "tipo_usuario": u.tipo_usuario,
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

        if "senha" in campos_enviados:
            u.hash_senha = ph.hash(campos_enviados["senha"])

        if tipo_mudou or any(
            c in campos_enviados
            for c in ("numero_crm", "uf_crm", "rqe", "numero_coren", "uf_coren", "especialidade")
        ):
            u.tipo_usuario = schema_completo.tipo_usuario
            u.atributos_profissionais_json = monta_atributos_json(schema_completo)

        return user.repo.save(u)