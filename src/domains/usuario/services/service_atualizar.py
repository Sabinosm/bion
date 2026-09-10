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
        valida os dois eixos independentes (eh_admin e tipo_papel, se
        houver mudança em algum deles), mescla os dados enviados com os
        atuais, revalida como cadastro completo e persiste.

        ALTERADO (separação admin/papel clínico, assertivo, sem alias):
        - tipo_usuario (3 valores mutuamente exclusivos) SAIU. Em seu
          lugar, dois eixos independentes: eh_admin (bool) e tipo_papel
          ("medico"/"enfermeiro"/None). Um usuário pode ter eh_admin=True
          e tipo_papel="medico" ao mesmo tempo.
        - Eixo eh_admin: nunca é alterado por edição de cadastro (nem
          promover, nem rebaixar), para qualquer solicitante, inclusive
          o super admin -- ver _valida_alteracao_admin. Virar admin só
          acontece via criar().
        - Eixo tipo_papel: troca de função clínica continua permitida
          via atualizar() -- ver _valida_troca_tipo.
        - Invariante nova: o usuário resultante nunca pode ficar com
          eh_admin=False e tipo_papel=None simultaneamente (ficaria sem
          qualquer acesso no sistema). Isso é impossível de expressar
          no schema de update parcial isolado (depende do estado atual
          mesclado com o payload), por isso é checado aqui.

        ALTERADO (múltiplos admins por empresa, preexistente):
        - Novo parâmetro `solicitante_eh_super_admin`, repassado para
          `_valida_permissao_edicao` -- só o super admin pode alterar um
          usuário que já é admin (comum ou super). Ver docstring de
          `_valida_permissao_edicao` em service_validacoes.py.

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
                validação, campos ausentes, tentativa de mexer em
                eh_admin, usuário resultante sem admin e sem papel, ou
                schema inválido.
            ConflictoError: se o novo CPF, e-mail ou login já existirem.
        """

        u = user.buscar_por_uuid(uuid)
        eh_auto_edicao = (uuid == solicitante_uuid)
    
        user._valida_permissao_edicao(
            dados, solicitante_eh_admin, solicitante_eh_super_admin, eh_auto_edicao, u
        )
    
        atributos_atuais_u = atributos_atuais(u)  # já devolve no formato antigo (numero-crm etc)

        # ALTERADO (separação admin/papel clínico, assertivo): antes
        # havia um único eixo (tipo_usuario, 3 valores mutuamente
        # exclusivos). Agora são DOIS eixos independentes, cada um
        # podendo mudar ou não, em qualquer combinação:
        eh_admin_atual = u.is_admin
        novo_eh_admin = dados.get("eh_admin", eh_admin_atual)
        admin_mudou = novo_eh_admin != eh_admin_atual

        papel_atual_tipo = u.funcao_clinica  # antes: tipo_atual = u.tipo_usuario
        novo_papel_tipo = dados.get("tipo_papel", papel_atual_tipo)
        papel_mudou = novo_papel_tipo != papel_atual_tipo

        # Eixo eh_admin: cargo de admin nunca muda por edição de
        # cadastro (nem promover, nem rebaixar) -- incondicional, para
        # qualquer solicitante, inclusive o super admin.
        user._valida_alteracao_admin(eh_admin_atual, novo_eh_admin, admin_mudou)

        # Eixo tipo_papel: troca de função clínica continua permitida
        # (médico <-> enfermeiro <-> nenhuma), com as exigências de
        # registro profissional de sempre.
        user._valida_troca_tipo(papel_atual_tipo, novo_papel_tipo, papel_mudou, dados)

        # ADICIONADO: invariante que não existia como risco antes
        # (tipo_usuario de 3 valores garantia isso por construção).
        # O usuário RESULTANTE desta atualização nunca pode ficar sem
        # ser admin e sem função clínica ao mesmo tempo -- senão vira
        # um usuário sem qualquer acesso no sistema (nem requer_admin
        # nem requer_papel_clinico o autorizam para nada).
        #
        # DECISÃO CONFIRMADA: isso dispara mesmo para edições que não
        # tocam eh_admin/tipo_papel (ex: só telefone), SE o usuário já
        # estiver inconsistente por dado legado. É proposital -- bloqueia
        # qualquer edição até alguém corrigir eh_admin/tipo_papel
        # primeiro, em vez de permitir que o estado inconsistente
        # continue sendo persistido silenciosamente.
        if not novo_eh_admin and novo_papel_tipo is None:
            raise DadosInvalidosError(
                "O usuário resultante ficaria sem ser administrador e sem "
                "função clínica. Defina 'eh_admin' ou 'tipo_papel'."
            )
    
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
            "eh_admin": eh_admin_atual,
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
    
        if "senha" in campos_enviados:
            u.hash_senha = ph.hash(campos_enviados["senha"])
    
        # -----------------------------------------------------------------
        # ALTERADO: troca de tipo / atualização de dados profissionais.
        # Antes: sobrescrevia atributos_profissionais_json inteiro.
        # Agora: opera sobre a linha de PapelProfissional.
        #
        # Nota (separação admin/papel clínico): u.is_admin nunca é
        # tocado neste bloco -- isso já foi validado incondicionalmente
        # por _valida_alteracao_admin acima (admin_mudou levanta erro
        # antes de chegar aqui). Este bloco cuida só do eixo tipo_papel.
        # -----------------------------------------------------------------
        
        campos_papel_mudaram = any(
            c in campos_enviados
            for c in ("numero_crm", "uf_crm", "rqe", "numero_coren", "uf_coren", "especialidade")
        )
    
        if papel_mudou or campos_papel_mudaram:
            papel_atual = u.papel_ativo()
    
            if papel_mudou and papel_atual:
                # Função clínica mudou (ex: enfermeiro virou médico, ou
                # perdeu a função clínica): desativa o papel antigo em
                # vez de apagar — preserva histórico (quem já teve qual
                # papel, quando).
                papel_atual.ativo = False
    
            dados_papel_novos = monta_dados_papel(schema_completo)
    
            if dados_papel_novos:
                if papel_mudou or not papel_atual:
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