from abc import ABC, abstractmethod
from ..repository import UsuarioRepository

class usuario(ABC):
    def __init__(
        self,
        id: int,
        uuid: str,
        id_empresa: int,
        nome_completo: str,
        cpf: str,
        tipo_usuario: str,
        status: str,
        hash_senha: str,
        email: str,
        user_login: str,
        ):
        
        self.id = id
        self.uuid = uuid
        self.id_empresa = id_empresa
        self.nome_completo = nome_completo 
        self.cpf = cpf
        self.tipo_usuario = tipo_usuario
        self.status = status
        self.hash_senha = hash_senha
        self.email = email
        self.user_login = user_login

    @abstractmethod
    def buscar_por_uuid(self, uuid: str):
        pass

    @abstractmethod
    def listar(self):
        pass

    @abstractmethod
    def listar_por_empresa(self, id_empresa: int):
        pass

    @abstractmethod
    def criar(self, dados: dict):
        pass

    @abstractmethod
    def atualizar(self, uuid: str, dados: dict):
        pass

    @abstractmethod
    def tipo_usuario(self,uuid:str):
        pass