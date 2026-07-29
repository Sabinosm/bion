"""Regras de negócio do domínio Usuario.

Este módulo concentra o CRUD principal (`UsuarioService`). As rotinas de
reset de credenciais vivem em `service_reset.py` (mixin) e as funções
puras de apoio em `service_helpers.py`, para manter este arquivo restrito
à orquestração das regras de criação/atualização de usuário.
"""

from src.core.security import ph, aes_encrypt, hmac_sha256, aes_decrypt
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from ..repository import UsuarioRepository
from .service_helpers import (
    CAMPOS_SIMPLES_ATUALIZAVEIS,
    CAMPOS_RESTRITOS_A_ADMIN,
    atributos_atuais,
    monta_dados_papel,
)
from .service_atualizar import att
from .service_reset import ResetCredenciaisMixin
from src.schemas.schema_usuario import CadastroUsuarioSchema, AtualizacaoUsuarioSchema
from src.models.usuarios import Usuario
from src.models.usuarios.papel_profissional import PapelProfissional
from src.models import db
from .service_validacoes import _checar_duplicidade, _valida_permissao_edicao, _valida_troca_tipo

class UsuarioService(ResetCredenciaisMixin):
    """Serviço de domínio para o CRUD de usuários e regras associadas."""
 
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
 
    def listar(self, id_empresa):
        """Lista todos os usuários de uma empresa.

        Parâmetros:
            id_empresa: identificador da empresa.

        Retorno:
            Lista de instâncias de Usuario.
        """
        return self.repo.find_all(id_empresa)
 
    def criar(self, id_empresa, dados: dict, commitar: bool = True):
        """Cria um novo usuário para a empresa informada.
 
        Parâmetros:
            id_empresa: identificador da empresa dona do cadastro.
            dados: dicionário bruto de entrada, validado internamente
                via CadastroUsuarioSchema.
            commitar: se True, persiste e comita a transação imediatamente.
 
        Retorno:
            Instância de Usuario criada e salva (com .papeis já populado
            se aplicável).
 
        Levanta:
            DadosInvalidosError: se `dados` não passar na validação do schema.
            ConflictoError: se CPF, e-mail ou login já existirem.
        """
        try:
            schema = CadastroUsuarioSchema(**dados)
        except Exception as e:
            raise DadosInvalidosError(f"Erro de validação: {e}") from e
 
        cpf_hash = hmac_sha256(schema.cpf)
        _checar_duplicidade(cpf_hash=cpf_hash, email=schema.email, login=schema.user_login)
 
        u = Usuario(
            id_empresa=id_empresa,
            nome_completo=schema.nome_completo,
            cpf=aes_encrypt(schema.cpf),
            cpf_hash=cpf_hash,
            email=schema.email,
            telefone=schema.telefone,
            user_login=schema.user_login,
            is_admin_flag=(schema.tipo_usuario == "admin"),
        )
 
        dados_papel = monta_dados_papel(schema)
        if dados_papel:
            # Associa via relationship, não via FK manual — o SQLAlchemy
            # resolve o id_usuario sozinho no flush/commit, mesmo que
            # 'u' ainda não tenha id definitivo neste ponto (útil
            # justamente no caso commitar=False citado acima).
            u.papeis.append(PapelProfissional(**dados_papel))
 
        return self.repo.save(u, commitar)
 
    def desativar(self, uuid: str):
        """Desativa um usuário, definindo seu status como 'inativo'.

        Parâmetros:
            uuid: identificador do usuário a desativar.

        Retorno:
            Instância de Usuario atualizada e salva.
        """    
        
        u = self.buscar_por_uuid(uuid)
        u.status = "inativo"
        return self.repo.save(u)
 
    def ativar(self, uuid: str):
        """Reativa um usuário, definindo seu status como 'ativo'.

        Parâmetros:
            uuid: identificador do usuário a ativar.

        Retorno:
            Instância de Usuario atualizada e salva.
        """
        u = self.buscar_por_uuid(uuid)
        u.status = "ativo"
        return self.repo.save(u)
 
    def atualizar(self, uuid: str, dados: dict, solicitante_eh_admin: bool, solicitante_uuid: str):
        return att(self, uuid, dados, solicitante_eh_admin, solicitante_uuid)
 