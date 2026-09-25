"""Regras de negócio do domínio Usuario.

Este módulo concentra o CRUD principal (`UsuarioService`), incluindo as
rotinas de reset de credenciais (reset_2fa/reset_total). As funções
puras de apoio ficam em `service_helpers.py`; as validações de
autorização em `service_validacoes.py`; a atualização parcial em
`service_atualizar.py`.

is_admin e tipo_papel são eixos independentes: um usuário pode ter
is_admin=True e tipo_papel="medico" ao mesmo tempo (admin que também
atende), e passa pelas mesmas regras de super admin/senha que um admin
puro. Criar um usuário com is_admin=True exige que o solicitante seja o
super admin, exceto na criação do primeiro admin de uma empresa nova
(ver Empresa.cadastrar_com_admin, único fluxo que passa
is_super_admin=True). Um usuário que já é admin só pode ser
desativado/ativado/resetado pelo super admin; o próprio super admin
nunca pode ser desativado ou resetado, por ninguém.

alterar_senha() é autoatendimento, chamado pelo próprio usuário já
reconfirmado via step-up no controller (este método não reautentica
nada, só valida força/repetição e persiste). resetar_senha_usuario() é
o reset feito por um super admin na conta de terceiro: não existe
conceito de "senha temporária" gerada pelo sistema, pois isso daria ao
admin uma senha válida da conta de outra pessoa; em vez disso o reset
zera hash_senha e devolve o usuário ao onboarding, para que ele mesmo
defina a nova senha. Ambas incrementam senha_versao, o que torna
qualquer sessão aberta com versão antiga detectável pelas rotas de
leitura sensível decoradas com `@requer_senha_atualizada` (session.py).
"""

from argon2.exceptions import VerifyMismatchError
from pydantic import ValidationError

from src.core.security import ph, aes_encrypt, hmac_sha256
from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ..repository import UsuarioRepository
from .service_helpers import monta_dados_papel
from .service_atualizar import att
from .service_reset import ResetCredenciaisMixin
from src.domains.usuario.schema_usuario import CadastroUsuarioSchema, AlterarSenhaSchema, _formatar_erros_pydantic
from src.models.usuarios import Usuario
from src.models.usuarios.papel_profissional import PapelProfissional
from .service_validacoes import (
    _checar_duplicidade,
    _valida_permissao_edicao,
    _valida_troca_tipo,
    _valida_alteracao_admin,
)


class UsuarioService(ResetCredenciaisMixin):
    """Serviço de domínio para o CRUD de usuários e regras associadas.

    Os métodos de reset de credenciais (reset_2fa, reset_total,
    resetar_senha_usuario) vêm de ResetCredenciaisMixin (service_reset.py).
    """

    _checar_duplicidade = _checar_duplicidade
    _valida_permissao_edicao = _valida_permissao_edicao
    _valida_troca_tipo = _valida_troca_tipo
    _valida_alteracao_admin = _valida_alteracao_admin

    def __init__(self):
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

    def listar(self, id_empresa, offset: int = 0, especialidade: str = 0, status: str = 0):
        """Lista todos os usuários de uma empresa.

        Parâmetros:
            id_empresa: identificador da empresa.

        Retorno:
            Lista de instâncias de Usuario.
        """
        return self.repo.find_all_param(id_empresa=id_empresa, offset=offset, especialidade=especialidade, status=status)

    def criar(
        self,
        id_empresa,
        dados: dict,
        commitar: bool = True,
        solicitante_eh_super_admin: bool = False,
        is_super_admin: bool = False,
    ):
        """Cria um novo usuário para a empresa informada.

        Parâmetros:
            id_empresa: identificador da empresa dona do cadastro.
            dados: dicionário bruto de entrada, validado internamente
                via CadastroUsuarioSchema.
            commitar: se True, persiste e comita a transação imediatamente.
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
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

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
            # Associa via relationship, não via FK manual -- o SQLAlchemy
            # resolve o id_usuario sozinho no flush/commit, mesmo que
            # 'u' ainda não tenha id definitivo neste ponto (relevante
            # quando commitar=False).
            u.papeis.append(PapelProfissional(**dados_papel))

        return self.repo.save(u, commitar)

    def desativar(self, uuid: str, solicitante_eh_super_admin: bool = False, commit: bool = True):
        """Desativa um usuário, definindo seu status como 'inativo'.

        Um usuário que já é admin (comum ou super) só pode ser
        desativado pelo super admin; o próprio super admin nunca pode
        ser desativado, por ninguém.

        Parâmetros:
            uuid: identificador do usuário a desativar.
            solicitante_eh_super_admin: se True, quem está pedindo é o
                super admin da empresa.

        Retorno:
            Instância de Usuario atualizada e salva.

        Levanta:
            DadosInvalidosError: se o alvo for admin e o solicitante não
                for o super admin, ou se o alvo for o próprio super admin.
        """
        u = self.buscar_por_uuid(uuid)

        if u.is_super_admin:
            raise DadosInvalidosError("O administrador principal não pode ser desativado.")

        if u.is_admin and not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode desativar um administrador."
            )

        u.status = "inativo"
        return self.repo.save(u, commit)  # commit feito via decorator de ação sensível

    def ativar(self, uuid: str, solicitante_eh_super_admin: bool = False):
        """Reativa um usuário, definindo seu status como 'ativo'.

        Mesma regra de desativar(): só o super admin ativa outro admin.

        Parâmetros:
            uuid: identificador do usuário a ativar.
            solicitante_eh_super_admin: se True, quem está pedindo é o
                super admin da empresa.

        Retorno:
            Instância de Usuario atualizada e salva, ou None se o
            usuário estiver 'pendente' (ativação manual não se aplica
            a esse status).

        Levanta:
            DadosInvalidosError: se o alvo for admin e o solicitante não
                for o super admin.
        """
        u = self.buscar_por_uuid(uuid)

        if u.is_admin and not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode ativar um administrador."
            )

        if u.status != "pendente":
            u.status = "ativo"
            return self.repo.save(u)
        return None

    def atualizar(
        self,
        uuid: str,
        dados: dict,
        solicitante_is_admin: bool,
        solicitante_uuid: str,
        solicitante_eh_super_admin: bool = False,
    ):
        return att(self, uuid, dados, solicitante_is_admin, solicitante_uuid, solicitante_eh_super_admin)

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
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

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
        return self.repo.count_no_super_admin_users(id_empresa=id_empresa)

    def contagem_profissionais_por_status(self, id_empresa, status):
        return self.repo.count_status_users(id_empresa=id_empresa, status=status)

    def efetivo_por_papel(self, id_empresa: int):
        """Contagem bruta de usuários ativos por papel (medico/enfermeiro/admin).
        Sem lógica de negócio aqui -- a leitura/texto fica na camada de
        estatística."""
        return self.repo.contar_ativos_por_papel(id_empresa=id_empresa)

    def inativos_ha_dias(self, id_empresa: int, dias: int = 7):
        return self.repo.contar_inativos_ha_dias(id_empresa=id_empresa, dias=dias)

    def lista_inativos_ha_dias(self, id_empresa: int, dias: int = 7):
        return self.repo.find_inativos_ha_dias(id_empresa=id_empresa, dias=dias)