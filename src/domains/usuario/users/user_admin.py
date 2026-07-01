import user_interface
from ..repository import UsuarioRepository
from src.core.security import ph, aes_encrypt, hmac_sha256
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
import json


CAMPOS_ATUALIZAVEIS = {
    "nome_completo", "email", "telefone"
}

class user_admin(user_interface):
    def __init__(
        self,
        id: int,
        uuid: str,
        id_empresa: int,
        nome_completo: str,
        cpf: str,
        status: str,
        hash_senha: str,
        email: str,
        user_login: str
        ):
        
        super().__init__(
            id=id,
            uuid=uuid,
            id_empresa=id_empresa,
            nome_completo=nome_completo,
            cpf=cpf,
            tipo_usuario='admin',
            status=status,
            hash_senha=hash_senha,
            email=email,
            user_login=user_login
        )
        
        self.id = id
        self.uuid = uuid
        self.id_empresa = id_empresa
        self.nome_completo = nome_completo 
        self.cpf = cpf
        self.tipo_usuario = 'admin'
        self.status = status
        self.hash_senha = hash_senha
        self.email = email
        self.user_login = user_login
        self.repo = UsuarioRepository()


    #admin não é listado
    def buscar_por_uuid(self):
        pass

    def listar(self):
        pass

    def listar_por_empresa(self):
        pass

    def criar(self):
        from src.database.usuarios import Usuario
        
        cpf_hash = hmac_sha256(self.cpf)
        if self.repo.find_by_cpf_hash(cpf_hash):
            raise ConflictoError("CPF já cadastrado para outro usuário.")

    
        u = Usuario(
            id_empresa=self.id_empresa,
            nome_completo=self.nome_completo,
            cpf=aes_encrypt(self.cpf),
            cpf_hash=cpf_hash,
            email=self.email,
            telefone=self.telefone,
            user_login=self.user_login,
            tipo_usuario=self.tipo_usuario,
            hash_senha=ph.hash(self.hash_senha),
            atributos_profissionais_json=None,
        )
        
        return self.repo.save(u)

    #TODO adicionar mais segurança na atualização de senhas, pedir 2FA
    def atualizar(self,  dados: dict):
        u = self.repo.find_by_uuid(self.uuid)
        for campo in CAMPOS_ATUALIZAVEIS:
            if campo in dados:
                setattr(u, campo, dados[campo])
        if "senha" in dados and dados["senha"]:
            u.hash_senha = ph.hash(dados["senha"])
        return self.repo.save(u)

    #TODO pedir 2FA
    def desativar(self, uuid_do_alvo: str):
        u = self.repo.find_by_uuid(uuid_do_alvo)
        u.status = "inativo"
        return self.repo.save(u)
    
    #TODO pedir 2FA        
    def ativar(self, uuid_do_alvo: str):
        u = self.repo.find_by_uuid(uuid_do_alvo)
        u.status = "ativo"
        return self.repo.save(u)