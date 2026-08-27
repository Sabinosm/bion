from src.core.security import ph, aes_encrypt, hmac_sha256, aes_decrypt
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from ..repository import UsuarioRepository
from .service_helpers import (
    CAMPOS_SIMPLES_ATUALIZAVEIS,
    CAMPOS_RESTRITOS_A_ADMIN,
    atributos_atuais,
    monta_dados_papel,
)
from .service_reset import ResetCredenciaisMixin
from src.schemas.schema_usuario import CadastroUsuarioSchema, AtualizacaoUsuarioSchema
from src.models.usuarios import Usuario
from src.models.usuarios.papel_profissional import PapelProfissional


def att(
    user,
    uuid: str,
    dados: dict,
    solicitante_eh_admin: bool,
    solicitante_uuid: str,
    solicitante_eh_super_admin: bool = False,
):
        """Atualiza parcialmente os dados de um usuário existente.

        Orquestra a atualização em etapas: valida permissão de edição,
        valida troca de tipo profissional (se houver), mescla os dados
        enviados com os atuais, revalida como cadastro completo e persiste.

        ALTERADO (múltiplos admins por empresa):
        - Novo parâmetro `solicitante_eh_super_admin`, repassado para
          `_valida_permissao_edicao` -- só o super admin pode alterar um
          usuário que já é admin (comum ou super). Ver docstring de
          `_valida_permissao_edicao` em service_validacoes.py.
        - Troca de/para tipo_usuario == "admin" agora é bloqueada de
          forma incondicional, para qualquer solicitante (inclusive o
          super admin) -- promover a admin só acontece via criar(), e
          rebaixar um admin nunca é permitido. Isso substitui a antiga
          checagem de auto-edição (que só cobria o solicitante editando
          a si mesmo); agora cobre também um admin tentando editar o
          tipo de outro usuário para admin, ou tentando rebaixar
          qualquer admin.

        Parâmetros:
            user: instância de UsuarioService que chamou esta função
                (não confundir com o model Usuario -- 'user' é o
                service, de onde vêm self.repo, self._checar_duplicidade
                etc; o registro do usuário sendo atualizado é a
                variável local 'u' logo abaixo).
            uuid: identificador do usuário a atualizar.
            dados: dicionário parcial com os campos a alterar.
            solicitante_eh_admin: se True, o solicitante pode alterar
                campos restritos.
            solicitante_uuid: UUID de quem está fazendo a requisição,
                usado para detectar auto-edição.
            solicitante_eh_super_admin: se True, o solicitante é o
                administrador principal da empresa -- necessário para
                alterar outro admin.

        Retorno:
            Instância de Usuario atualizada e salva.

        Levanta:
            DadosInvalidosError: em qualquer violação das regras de
                validação, campos ausentes, tentativa de mexer em tipo
                admin, ou schema inválido.
            ConflictoError: se o novo CPF, e-mail ou login já existirem.
        """

        u = user.buscar_por_uuid(uuid)
        eh_auto_edicao = (uuid == solicitante_uuid)
    
        user._valida_permissao_edicao(
            dados, solicitante_eh_admin, solicitante_eh_super_admin, eh_auto_edicao, u
        )
    
        atributos_atuais_u = atributos_atuais(u)  # já devolve no formato antigo (numero-crm etc)
        tipo_atual = u.tipo_usuario  # agora é @property, acesso idêntico a antes
        novo_tipo = dados.get("tipo_usuario", tipo_atual)
        tipo_mudou = novo_tipo != tipo_atual

        # ADICIONADO: cargo de admin nunca é alterado por edição de
        # cadastro -- nem promover (médico/enfermeiro -> admin), nem
        # rebaixar (admin -> médico/enfermeiro/qualquer coisa). Virar
        # admin só acontece em criar() (novo cadastro), restrito ao
        # super admin. Verificação incondicional: vale para qualquer
        # solicitante, inclusive o próprio super admin.
        if tipo_mudou and (tipo_atual == "admin" or novo_tipo == "admin"):
            raise DadosInvalidosError(
                "O cargo de administrador não pode ser alterado por edição de cadastro."
            )

        user._valida_troca_tipo(tipo_atual, novo_tipo, tipo_mudou, dados)
    
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
            "tipo_usuario": tipo_atual,
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
    
        # -----------------------------------------------------------------
        # ALTERADO: troca de tipo / atualização de dados profissionais.
        # Antes: sobrescrevia atributos_profissionais_json inteiro.
        # Agora: opera sobre a linha de PapelProfissional.
        #
        # Nota (múltiplos admins): como tipo_mudou envolvendo "admin" já
        # levantou DadosInvalidosError acima, tudo que chega até aqui com
        # tipo_mudou=True é troca médico <-> enfermeiro -- u.is_admin
        # nunca é tocado neste bloco.
        # -----------------------------------------------------------------
        
        campos_papel_mudaram = any(
            c in campos_enviados
            for c in ("numero_crm", "uf_crm", "rqe", "numero_coren", "uf_coren", "especialidade")
        )
    
        if tipo_mudou or campos_papel_mudaram:
            papel_atual = u.papel_ativo()
    
            if tipo_mudou and papel_atual:
                # Tipo profissional mudou (ex: enfermeiro virou médico):
                # desativa o papel antigo em vez de apagar — preserva
                # histórico (quem já teve qual papel, quando).
                papel_atual.ativo = False
    
            dados_papel_novos = monta_dados_papel(schema_completo)
    
            if dados_papel_novos:
                if tipo_mudou or not papel_atual:
                    # Papel novo (troca de tipo médico <-> enfermeiro, ou
                    # usuário que ainda não tinha papel algum)
                    novo_papel = PapelProfissional(**dados_papel_novos)
                    u.papeis.append(novo_papel)
                else:
                    # Mesmo tipo, só atualizando CRM/COREN/especialidade
                    # do papel já existente — atualiza em vez de duplicar
                    for campo, valor in dados_papel_novos.items():
                        setattr(papel_atual, campo, valor)
    
        return user.repo.save(u)