"""Regras de negócio do domínio Usuario.

Este módulo concentra o CRUD principal (`UsuarioService`). As rotinas de
reset de credenciais vivem em `service_reset.py` (mixin) e as funções
puras de apoio em `service_helpers.py`, para manter este arquivo restrito
à orquestração das regras de criação/atualização de usuário.

ALTERADO (múltiplos admins por empresa):
- `criar()`: criar um usuário com tipo_usuario="admin" agora exige que o
  solicitante seja o super admin (ou que a criação já venha marcada como
  `is_super_admin=True`, único caso sendo o primeiro admin de uma
  empresa nova -- ver Empresa.cadastrar_com_admin). Sem isso, um admin
  comum poderia criar outros admins livremente, o que quebraria a
  hierarquia combinada (só o super admin cria admin).
- `desativar()`/`ativar()`: um usuário que já é admin só pode ser
  desativado/ativado pelo super admin; o próprio super admin nunca pode
  ser desativado, por ninguém.
"""

from src.core.security import ph, aes_encrypt, hmac_sha256
from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from ..repository import UsuarioRepository
from .service_helpers import (
    monta_dados_papel,
)
from .service_atualizar import att
from .service_reset import ResetCredenciaisMixin
from src.schemas.schema_usuario import CadastroUsuarioSchema
from src.models.usuarios import Usuario
from src.models.usuarios.papel_profissional import PapelProfissional
from .service_validacoes import _checar_duplicidade, _valida_permissao_edicao, _valida_troca_tipo

class UsuarioService(ResetCredenciaisMixin):
    """Serviço de domínio para o CRUD de usuários e regras associadas."""

    # ALTERADO: _checar_duplicidade / _valida_permissao_edicao /
    # _valida_troca_tipo são definidas em service_validacoes.py como
    # funções soltas de módulo (não dentro de uma classe), mas com
    # 'self' como primeiro parâmetro -- ou seja, foram escritas para
    # funcionar como métodos. Atribuí-las aqui como atributos de classe
    # é o que faz `self._checar_duplicidade(...)` (chamado neste
    # arquivo) e `user._checar_duplicidade(...)` (chamado em
    # service_atualizar.py, onde 'user' é uma instância desta mesma
    # classe) funcionarem de fato como métodos vinculados, sem precisar
    # copiar essas funções para dentro da classe ou mudar sua
    # assinatura em service_validacoes.py.
    _checar_duplicidade = _checar_duplicidade
    _valida_permissao_edicao = _valida_permissao_edicao
    _valida_troca_tipo = _valida_troca_tipo
 
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
 
    def listar(self, id_empresa, offset:int = 0, especialidade:str = 0, status:str = 0):
        """Lista todos os usuários de uma empresa.

        Parâmetros:
            id_empresa: identificador da empresa.

        Retorno:
            Lista de instâncias de Usuario.
        """
        return self.repo.find_all_param(id_empresa=id_empresa, offset=offset, especialidade=especialidade,status=status)
    
    
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
                criar um usuário com tipo_usuario="admin". Ignorado para
                médico/enfermeiro.
            is_super_admin: marca o usuário recém-criado como super
                admin. Só deve ser True vindo de
                Empresa.cadastrar_com_admin (criação do primeiro admin
                de uma empresa nova) -- nunca a partir de uma requisição
                de um admin já autenticado.
 
        Retorno:
            Instância de Usuario criada e salva (com .papeis já populado
            se aplicável).
 
        Levanta:
            DadosInvalidosError: se `dados` não passar na validação do
                schema, ou se um usuário admin estiver sendo criado por
                quem não é o super admin.
            ConflictoError: se CPF, e-mail ou login já existirem.
        """
        try:
            schema = CadastroUsuarioSchema(**dados)
        except Exception as e:
            raise DadosInvalidosError(f"Erro de validação: {e}") from e

        # ADICIONADO: só o super admin cria outros admins. is_super_admin=True
        # (fluxo de Empresa.cadastrar_com_admin, sem solicitante autenticado)
        # também libera -- é a criação do próprio super admin fundador.
        if schema.tipo_usuario == "admin" and not solicitante_eh_super_admin and not is_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode criar novos administradores."
            )
 
        cpf_hash = hmac_sha256(schema.cpf)
        self._checar_duplicidade(cpf_hash=cpf_hash, email=schema.email, login=schema.user_login)

        # ALTERADO: Usuario(...) era instanciado só dentro do
        # 'if tipo_usuario == "admin"', então médico/enfermeiro batiam
        # em NameError na linha 'u.papeis.append(...)' logo abaixo (a
        # variável 'u' nunca chegava a existir para esses tipos). O
        # cadastro precisa da linha em Usuario para qualquer tipo --
        # o que muda por tipo é só a associação de PapelProfissional,
        # que já é tratada à parte, no bloco 'dados_papel' abaixo.
        
        u = Usuario(
            id_empresa=id_empresa,
            nome_completo=schema.nome_completo,
            cpf=aes_encrypt(schema.cpf),
            cpf_hash=cpf_hash,
            email=schema.email,
            telefone=schema.telefone,
            user_login=schema.user_login,
            is_admin=(schema.tipo_usuario == "admin"),
            is_super_admin=is_super_admin,
            # ALTERADO: schema.hash_senha não existe -- o schema expõe
            # 'senha' em texto puro (validada, não hasheada); o hash é
            # responsabilidade de quem consome o schema, mesmo padrão
            # já usado para CPF (aes_encrypt/hmac_sha256 aqui do lado
            # de fora, não dentro do schema).
            # 'senha' agora só vem preenchida para admin -- o schema
            # garante isso (obrigatória para admin, proibida para
            # médico/enfermeiro). Para médico/enfermeiro, hash_senha
            # fica None: o acesso desses usuários é definido depois,
            # em um fluxo de ativação de conta separado.
            hash_senha=ph.hash(schema.senha) if schema.senha else None,
        )
 
        dados_papel = monta_dados_papel(schema)
        if dados_papel:
            # Associa via relationship, não via FK manual — o SQLAlchemy
            # resolve o id_usuario sozinho no flush/commit, mesmo que
            # 'u' ainda não tenha id definitivo neste ponto (útil
            # justamente no caso commitar=False citado acima).
            u.papeis.append(PapelProfissional(**dados_papel))
 
        return self.repo.save(u, commitar)
 
    def desativar(self, uuid: str, solicitante_eh_super_admin: bool = False):
        """Desativa um usuário, definindo seu status como 'inativo'.

        ALTERADO (múltiplos admins por empresa): um usuário que já é
        admin (comum ou super) só pode ser desativado pelo super admin;
        o próprio super admin nunca pode ser desativado, por ninguém.

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
        return self.repo.save(u, False) # -> Commit feito via decorator ação sensível
 
    def ativar(self, uuid: str, solicitante_eh_super_admin: bool = False):
        """Reativa um usuário, definindo seu status como 'ativo'.

        ALTERADO (múltiplos admins por empresa): mesma regra de
        desativar() -- só o super admin ativa outro admin.

        Parâmetros:
            uuid: identificador do usuário a ativar.
            solicitante_eh_super_admin: se True, quem está pedindo é o
                super admin da empresa.

        Retorno:
            Instância de Usuario atualizada e salva.

        Levanta:
            DadosInvalidosError: se o alvo for admin e o solicitante não
                for o super admin.
        """
        u = self.buscar_por_uuid(uuid)

        if u.is_admin and not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode ativar um administrador."
            )

        if u.status !="pendente":
            u.status = "ativo"
            return self.repo.save(u)
        return None
        
    
    def atualizar(
        self,
        uuid: str,
        dados: dict,
        solicitante_eh_admin: bool,
        solicitante_uuid: str,
        solicitante_eh_super_admin: bool = False,
    ):
        return att(self, uuid, dados, solicitante_eh_admin, solicitante_uuid, solicitante_eh_super_admin)
    
    def contagem_profissionais(self, id_empresa):
        return self.repo.count_no_super_admin_users(id_empresa=id_empresa)
    
    def contagem_profissionais_por_status(self, id_empresa, status):
        return self.repo.count_status_users(id_empresa=id_empresa, status=status)

    # --- A4: Efetivo ativo por papel ---
    def efetivo_por_papel(self, id_empresa: int):
        """Repassa a contagem bruta por papel (medico/enfermeiro/admin).
        Sem lógica de negócio aqui -- a leitura/texto fica na camada de
        estatística."""
        return self.repo.contar_ativos_por_papel(id_empresa=id_empresa)
    
        # --- A5: Engajamento/atividade da equipe ---
    def inativos_ha_dias(self, id_empresa: int, dias: int = 7):
        return self.repo.contar_inativos_ha_dias(id_empresa=id_empresa, dias=dias)
 
    def lista_inativos_ha_dias(self, id_empresa: int, dias: int = 7):
        return self.repo.find_inativos_ha_dias(id_empresa=id_empresa, dias=dias)