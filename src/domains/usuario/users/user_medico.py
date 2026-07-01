import user_interface
from ..repository import UsuarioRepository
from src.core.security import ph, aes_encrypt, hmac_sha256
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
import json


CAMPOS_ATUALIZAVEIS = {
    "nome_completo", "email", "telefone"
}

class user_enfermeiro(user_interface):
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
        user_login: str,
        #dados importantes para o enfermeiro
        numero_crm: int,
        uf_crm: str,
        rqe: str=None,
        
        ):
        
        super().__init__(
            id=id,
            uuid=uuid,
            id_empresa=id_empresa,
            nome_completo=nome_completo,
            cpf=cpf,
            tipo_usuario='enfermeiro',
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
        self.tipo_usuario = 'enfermeiro'
        self.status = status
        self.hash_senha = hash_senha
        self.email = email
        self.user_login = user_login
        self.repo = UsuarioRepository()
        self.rqe = rqe
        self.numero_crm = numero_crm
        self.uf_crm = uf_crm

    def buscar_por_uuid(self):
        u = self.repo.find_by_uuid(self.uuid)
        if not u:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado: {self.uuid}")
        return u

    def listar(self):
        return self.repo.find_all()

    def listar_por_empresa(self):
        return self.repo.find_por_empresa(self.id_empresa)

    def criar(self):
        from src.database.usuarios import Usuario

        
        # obrigatorios = ("id_empresa", "nome_completo", "cpf", "email",
        #                 "user_login", "tipo_usuario", "senha",
        #                 #informacoes do profissional
        #                 'numero_crm','uf_crm','rqe')
        
        # faltando = [c for c in obrigatorios if not dados.get(c)]
        # if faltando:
        #     raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")

        if self.repo.find_by_login(self.user_login):
            raise ConflictoError("Login já em uso.")
        if self.repo.find_by_email(self.email):
            raise ConflictoError("E-mail já em uso.")
        cpf_hash = hmac_sha256(self.cpf)
        if self.repo.find_by_cpf_hash(cpf_hash):
            raise ConflictoError("CPF já cadastrado para outro usuário.")

        #TODO garantir que esses dados estejam na tipagem correta
        atributos={
            "numero_crm": self.numero_crm,
            "uf_crm": self.uf_crm,
            "rqe": self.rqe
        }
    
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
            atributos_profissionais_json=json.dumps(atributos),
        )
        
        return self.repo.save(u)
    
    #TODO adicionar mais segurança na atualização de senhas, pedir 2FA
    def atualizar(self,  dados: dict):
        u = self.buscar_por_uuid(self.uuid)
        for campo in CAMPOS_ATUALIZAVEIS:
            if campo in dados:
                setattr(u, campo, dados[campo])
        if "senha" in dados and dados["senha"]:
            u.hash_senha = ph.hash(dados["senha"])
        return self.repo.save(u)

    