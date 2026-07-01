"""
Regras de negocio do dominio Usuario.

Mantidos `criar` e `desativar` do original, e adicionados `atualizar` e
`ativar` -- o controller original tinha uma rota GET /editar (so
renderizava o form) sem nenhum POST correspondente no service; como
service e controller foram unificados, o metodo de update precisava
existir de fato.
"""

from src.core.security import ph, aes_encrypt, hmac_sha256
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from .repository import UsuarioRepository

CAMPOS_ATUALIZAVEIS = {
    "nome_completo", "email", "telefone"
}


class UsuarioService:

    def __init__(self):
        self.repo = UsuarioRepository()
        

    def buscar_por_uuid(self, uuid: str):
        u = self.repo.find_by_uuid(uuid)
        if not u:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado: {uuid}")
        return u

    def listar(self):
        return self.repo.find_all()

    def listar_por_empresa(self, id_empresa: int):
        return self.repo.find_por_empresa(id_empresa)

    def criar(self, dados: dict):
        from src.database.usuarios import Usuario

        obrigatorios = ("id_empresa", "nome_completo", "cpf", "email",
                        "user_login", "tipo_usuario", "senha")
        faltando = [c for c in obrigatorios if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")

        if self.repo.find_by_login(dados["user_login"]):
            raise ConflictoError("Login já em uso.")
        if self.repo.find_by_email(dados["email"]):
            raise ConflictoError("E-mail já em uso.")
        cpf_hash = hmac_sha256(dados["cpf"])
        if self.repo.find_by_cpf_hash(cpf_hash):
            raise ConflictoError("CPF já cadastrado para outro usuário.")

        u = Usuario(
            id_empresa=dados["id_empresa"],
            nome_completo=dados["nome_completo"],
            cpf=aes_encrypt(dados["cpf"]),
            cpf_hash=cpf_hash,
            email=dados["email"],
            telefone=dados.get("telefone"),
            user_login=dados["user_login"],
            tipo_usuario=dados["tipo_usuario"],
            hash_senha=ph.hash(dados["senha"]),
            atributos_profissionais_json=dados.get("atributos"),
        )
        return self.repo.save(u)

    def atualizar(self, uuid: str, dados: dict):
        u = self.buscar_por_uuid(uuid)
        for campo in CAMPOS_ATUALIZAVEIS:
            if campo in dados:
                setattr(u, campo, dados[campo])
        if "senha" in dados and dados["senha"]:
            u.hash_senha = ph.hash(dados["senha"])
        return self.repo.save(u)

    def desativar(self, uuid: str):
        u = self.buscar_por_uuid(uuid)
        u.status = "inativo"
        return self.repo.save(u)

    def ativar(self, uuid: str):
        u = self.buscar_por_uuid(uuid)
        u.status = "ativo"
        return self.repo.save(u)

