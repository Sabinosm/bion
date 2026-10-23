"""service.py -- regras de negócio do domínio Usuario.

Concentra o CRUD de usuários (criação, listagem, ativação/desativação,
troca de senha, contagens para estatísticas e foto de perfil) e aplica
as regras de hierarquia entre administradores. A atualização parcial, as
validações de autorização e as rotinas de reset ficam em módulos
vizinhos, compostos aqui no service.

is_admin e tipo_papel (função clínica) são eixos independentes: um admin
pode também atender. Criar um admin exige o super admin, exceto na
criação do primeiro admin de uma empresa nova (fluxo de cadastro da
empresa, o único que cria o super admin). Um usuário que já é admin só
pode ser ativado, desativado ou resetado pelo super admin, e o próprio
super admin nunca pode ser desativado ou resetado.

A troca de senha pelo próprio usuário não reautentica (a prova de
identidade vem do step-up); o reset feito por um admin nunca gera senha
temporária: zera a senha e devolve o usuário ao onboarding. Ambos
incrementam senha_versao, o que invalida sessões antigas nas rotas
protegidas por `@requer_senha_atualizada` (session.py).
"""

from argon2.exceptions import VerifyMismatchError
from pydantic import ValidationError

from src.core.security import ph, aes_encrypt, hmac_sha256
from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ..repository import UsuarioRepository
from .service_helpers import monta_dados_papel
from .service_atualizar import att
from .service_reset import ResetCredenciaisMixin
from src.core.erros_pydantic import erros_pydantic_por_campo
from src.domains.usuario.schema_usuario import CadastroUsuarioSchema, AlterarSenhaSchema
from src.models.usuarios import Usuario
from src.models.usuarios.papel_profissional import PapelProfissional
from .service_validacoes import (
    _checar_duplicidade,
    _valida_permissao_edicao,
    _valida_troca_tipo,
    _valida_alteracao_admin,
)
from .service_storage_pfp import StorageService


class UsuarioService(ResetCredenciaisMixin, StorageService):
    """CRUD de usuários e regras associadas.

    Herda os resets de credencial de ResetCredenciaisMixin e o acesso ao
    storage de avatar de StorageService.
    """

    _checar_duplicidade = _checar_duplicidade
    _valida_permissao_edicao = _valida_permissao_edicao
    _valida_troca_tipo = _valida_troca_tipo
    _valida_alteracao_admin = _valida_alteracao_admin

    def __init__(self):
        super().__init__()  # sem isso o StorageService fica sem bucket/credenciais
        self.repo = UsuarioRepository()

    def buscar_por_uuid(self, uuid: str):
        """Busca um usuário pelo UUID.

        Parâmetros:
            uuid: identificador único do usuário.

        Retorno:
            Instância de Usuario correspondente.

        Levanta:
            RecursoNaoEncontradoError: se nenhum usuário for encontrado.
        """
        u = self.repo.find_by_uuid(uuid)
        if not u:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado: {uuid}")
        return u

    def buscar_por_id(self, id: int):
        """Busca um usuário pelo ID.

        Parâmetros:
            id: identificador único do usuário.

        Retorno:
            Instância de Usuario correspondente.

        Levanta:
            RecursoNaoEncontradoError: se nenhum usuário for encontrado.
        """
        u = self.repo.find_by_id(id)
        if not u:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado: {id}")
        return u

    def listar(self, id_empresa, offset: int = 0, especialidade: str | None = None, status: str | None = None):
        """Lista uma página de usuários da empresa (exceto o super admin).

        Parâmetros:
            id_empresa: identificador da empresa.
            offset: quantos registros pular (a página tem 8).
            especialidade: filtro opcional.
            status: filtro opcional ('pendente', 'ativo' ou 'inativo').

        Retorno:
            Query paginada de Usuario.
        """
        return self.repo.find_all_param(id_empresa=id_empresa, offset=offset, especialidade=especialidade, status=status)

    def buscar_por_uuid_da_empresa(self, uuid: str, id_empresa: int):
        """Busca um usuário pelo UUID, restrito a uma empresa.

        Um usuário de outra empresa é tratado como inexistente (e não
        como "acesso negado"), para não revelar que o uuid existe.

        Parâmetros:
            uuid: identificador único do usuário.
            id_empresa: empresa à qual o usuário precisa pertencer.

        Retorno:
            Instância de Usuario correspondente.

        Levanta:
            RecursoNaoEncontradoError: se não existir ou for de outra empresa.
        """
        u = self.buscar_por_uuid(uuid)
        if u.id_empresa != id_empresa:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado: {uuid}")
        return u

    def criar(
        self,
        id_empresa,
        dados: dict,
        commit: bool = True,
        solicitante_eh_super_admin: bool = False,
        is_super_admin: bool = False,
    ):
        """Cria um novo usuário para a empresa informada.

        Parâmetros:
            id_empresa: identificador da empresa dona do cadastro.
            dados: dicionário bruto de entrada, validado internamente
                via CadastroUsuarioSchema.
            commit: se True, persiste e comita a transação imediatamente.
            solicitante_eh_super_admin: se True, quem está pedindo a
                criação é o super admin da empresa -- necessário para
                criar um usuário com is_admin=True. Ignorado quando
                is_admin=False (médico/enfermeiro comuns).
            is_super_admin: marca o usuário recém-criado como super
                admin. Só deve ser True vindo de
                Empresa.cadastrar_com_admin (criação do primeiro admin
                de uma empresa nova) -- nunca a partir de uma requisição
                de um admin já autenticado. Só existe um super admin por
                empresa.

        Retorno:
            Instância de Usuario criada e salva (com .papeis já populado
            se aplicável).

        Levanta:
            DadosInvalidosError: se `dados` não passar na validação do
                schema, se um usuário admin estiver sendo criado por
                quem não é o super admin, ou se a presença/ausência de
                senha não corresponder ao esperado para o tipo de admin
                sendo criado (fundador vs. comum).
            ConflictoError: se CPF, e-mail ou login já existirem.
        """
        try:
            schema = CadastroUsuarioSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        # Só o super admin cria outros admins. is_super_admin=True (fluxo
        # de Empresa.cadastrar_com_admin, sem solicitante autenticado)
        # também libera -- é a criação do próprio super admin fundador.
        if schema.is_admin and not solicitante_eh_super_admin and not is_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode criar novos administradores."
            )

        # Obrigatoriedade/proibição de senha para admin depende de
        # is_super_admin (só chega True vindo de
        # Empresa.cadastrar_com_admin, nunca de payload de cliente).
        # Vale tanto para admin puro quanto para admin que também tem
        # tipo_papel preenchido.
        if schema.is_admin:
            if is_super_admin and not schema.senha:
                raise DadosInvalidosError(
                    "O administrador principal precisa definir uma senha no cadastro."
                )
            if not is_super_admin and schema.senha:
                raise DadosInvalidosError(
                    "Administradores não devem informar 'senha' no cadastro; o "
                    "acesso é definido em um fluxo de ativação de conta separado."
                )

        cpf_hash = hmac_sha256(schema.cpf)
        self._checar_duplicidade(cpf_hash=cpf_hash, email=schema.email, login=schema.user_login)

        u = Usuario(
            id_empresa=id_empresa,
            nome_completo=schema.nome_completo,
            cpf=aes_encrypt(schema.cpf),
            cpf_hash=cpf_hash,
            email=schema.email,
            telefone=schema.telefone,
            user_login=schema.user_login,
            is_admin=schema.is_admin,
            is_super_admin=is_super_admin,
            hash_senha=ph.hash(schema.senha) if schema.senha else None,
            onboarding_pendente=True,
        )

        dados_papel = monta_dados_papel(schema)
        if dados_papel:
            # Via relationship: o SQLAlchemy resolve id_usuario no flush,
            # mesmo sem commit (commit=False).
            u.papeis.append(PapelProfissional(**dados_papel))

        return self.repo.save(u, commit)

    def desativar(self, uuid: str, id_empresa_solicitante: int, solicitante_eh_super_admin: bool = False, commit: bool = True):
        """Desativa um usuário, definindo seu status como 'inativo'.

        Um usuário que já é admin (comum ou super) só pode ser
        desativado pelo super admin; o próprio super admin nunca pode
        ser desativado, por ninguém.

        Parâmetros:
            uuid: identificador do usuário a desativar.
            id_empresa_solicitante: empresa de quem pede; o alvo precisa
                pertencer a ela.
            solicitante_eh_super_admin: se True, quem está pedindo é o
                super admin da empresa.

        Retorno:
            Instância de Usuario atualizada e salva.

        Levanta:
            DadosInvalidosError: se o alvo for admin e o solicitante não
                for o super admin, ou se o alvo for o próprio super admin.
            RecursoNaoEncontradoError: alvo inexistente ou de outra empresa.
        """
        u = self.buscar_por_uuid_da_empresa(uuid, id_empresa_solicitante)

        if u.is_super_admin:
            raise DadosInvalidosError("O administrador principal não pode ser desativado.")

        if u.is_admin and not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode desativar um administrador."
            )

        u.status = "inativo"
        return self.repo.save(u, commit)  # com commit=False, quem fecha é o @acao_sensivel

    def ativar(self, uuid: str, id_empresa_solicitante: int, solicitante_eh_super_admin: bool = False, commit: bool = True):
        """Reativa um usuário, definindo seu status como 'ativo'.

        Mesma regra de desativar(): só o super admin ativa outro admin.

        Parâmetros:
            uuid: identificador do usuário a ativar.
            id_empresa_solicitante: empresa de quem pede; o alvo precisa
                pertencer a ela.
            solicitante_eh_super_admin: se True, quem está pedindo é o
                super admin da empresa.
            commit: se False, só faz flush (commit fica com quem chama).

        Retorno:
            Instância de Usuario atualizada e salva, ou None se o
            usuário estiver 'pendente' (ativação manual não se aplica
            a esse status).

        Levanta:
            DadosInvalidosError: se o alvo for admin e o solicitante não
                for o super admin.
            RecursoNaoEncontradoError: alvo inexistente ou de outra empresa.
        """
        u = self.buscar_por_uuid_da_empresa(uuid, id_empresa_solicitante)

        if u.is_admin and not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode ativar um administrador."
            )

        if u.status != "pendente":
            u.status = "ativo"
            return self.repo.save(u, commit)
        return None

    def atualizar(
        self,
        uuid: str,
        dados: dict,
        solicitante_is_admin: bool,
        solicitante_uuid: str,
        id_empresa_solicitante: int,
        solicitante_eh_super_admin: bool = False,
    ):
        """Atualiza parcialmente um usuário; ver `att` em service_atualizar.py
        para parâmetros, regras e exceções."""
        return att(
            self, uuid, dados, solicitante_is_admin, solicitante_uuid,
            id_empresa_solicitante, solicitante_eh_super_admin,
        )

    def alterar_senha(self, uuid: str, dados: dict, commit: bool = True):
        """Troca a senha do próprio usuário autenticado.

        Protegido a montante por step-up no controller (o token já foi
        consumido antes de chegar aqui) -- este método não reautentica
        nada, só valida força/repetição via schema e persiste.

        Parâmetros:
            uuid: uuid do usuário logado (g.uuid_usuario no controller
                -- nunca um uuid arbitrário vindo do payload, pra não
                abrir brecha de trocar a senha de outra pessoa por essa
                via).
            dados: dict bruto do payload, validado aqui via
                AlterarSenhaSchema.

        Retorno:
            Instância de Usuario atualizada e salva.

        Levanta:
            DadosInvalidosError: se a senha não passar na validação de
                força, ou se for igual à senha atual.
            RecursoNaoEncontradoError: se o uuid não corresponder a
                nenhum usuário (não deveria acontecer numa sessão válida,
                mas cobre a corrida de usuário deletado no meio do fluxo).
        """
        try:
            schema = AlterarSenhaSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        u = self.buscar_por_uuid(uuid)

        # Impede repetir a mesma senha -- só dá pra comparar via verify
        # (hash não é reversível), não via igualdade direta de string.
        if u.hash_senha:
            try:
                ph.verify(u.hash_senha, schema.senha_nova)
                raise DadosInvalidosError("A nova senha deve ser diferente da atual.")
            except VerifyMismatchError:
                pass

        u.hash_senha = ph.hash(schema.senha_nova)
        u.senha_versao = (u.senha_versao or 1) + 1
        u.deve_trocar_senha = False
        return self.repo.save(u, commit)

    def contagem_profissionais(self, id_empresa):
        """Total de usuários da empresa, sem contar o super admin."""
        return self.repo.count_no_super_admin_users(id_empresa=id_empresa)

    def contagem_profissionais_por_status(self, id_empresa, status):
        """Total de usuários (sem o super admin) com o status informado."""
        return self.repo.count_status_users(id_empresa=id_empresa, status=status)

    def efetivo_por_papel(self, id_empresa: int):
        """Contagem bruta de usuários ativos por papel (medico/enfermeiro/admin).

        A interpretação do resultado fica na camada de estatística."""
        return self.repo.contar_ativos_por_papel(id_empresa=id_empresa)

    def inativos_ha_dias(self, id_empresa: int, dias: int = 7) -> int:
        """Quantos usuários ativos estão sem acesso há mais de `dias` dias."""
        return self.repo.contar_inativos_ha_dias(id_empresa=id_empresa, dias=dias)

    def lista_inativos_ha_dias(self, id_empresa: int, dias: int = 7):
        """Lista os usuários ativos sem acesso há mais de `dias` dias."""
        return self.repo.find_inativos_ha_dias(id_empresa=id_empresa, dias=dias)

    def atualizar_avatar_usuario(self, id_usuario: int, file) -> Usuario:
        """Troca a foto de perfil: envia a nova, grava no banco e só então
        apaga a antiga do storage. Se a gravação no banco falhar, a nova
        é removida do storage e o erro é repropagado.

        Parâmetros:
            id_usuario: usuário dono do avatar.
            file: FileStorage do Flask com a imagem.

        Retorno:
            Instância de Usuario atualizada.

        Levanta:
            RecursoNaoEncontradoError: se o usuário não existir.
            DadosInvalidosError / BionException: ver upload_avatar.
        """
        usuario = self.buscar_por_id(id_usuario)
        avatar_antigo = usuario.avatar_filename

        novo_filename = self.upload_avatar(file)
        try:
            usuario = self.repo.salvar_pfp(usuario, novo_filename=novo_filename)
        except Exception:
            self.deletar_avatar(novo_filename)  # não deixa arquivo órfão no bucket
            raise

        if avatar_antigo and avatar_antigo != novo_filename:
            self.deletar_avatar(avatar_antigo)

        return usuario

    def verificar_avatar_usuario(self, id_usuario: int) -> dict:
        """Informa se o usuário tem foto de perfil e, se tiver, a URL pública.

        Só lê avatar_filename (já carregado em Usuario) e monta a URL pelo
        StorageService -- não faz chamada ao storage, então é barato.

        Retorno:
            {"tem_avatar": bool, "url": str | None}

        Levanta:
            RecursoNaoEncontradoError: se o usuário não existir mais.
        """
        usuario = self.buscar_por_id(id_usuario)
        filename = usuario.avatar_filename
        if not filename:
            return {"tem_avatar": False, "url": None}
        return {"tem_avatar": True, "url": self.url_avatar(filename)}

    def remover_avatar_usuario(self, id_usuario: int):
        """Remove a foto de perfil do banco e do storage.

        Retorno:
            Instância de Usuario atualizada, ou None se o usuário não
            existir ou não tiver avatar.
        """
        usuario, avatar_antigo = self.repo.deletar_pfp(id_usuario)

        if not usuario or not avatar_antigo:
            return None

        self.deletar_avatar(avatar_antigo)
        return usuario