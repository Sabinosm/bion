"""
ALTERADO: tipo_usuario deixou de ser coluna de Usuario (agora é
@property calculada). Isso significa que Usuario.query.filter_by(
tipo_usuario=...) NÃO FUNCIONA MAIS -- o SQLAlchemy não sabe traduzir
uma property Python em SQL sozinho.

Nenhum método existente aqui usava isso (find_all, find_by_login etc
filtram por outras colunas reais), então nada quebrou de fato -- mas
adicionei find_by_tipo_papel() como o substituto correto, para uso
futuro caso precise (ex: "listar todos os médicos da empresa").
"""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.usuarios import Usuario
from src.models.usuarios.papel_profissional import PapelProfissional


class UsuarioRepository(IRepository[Usuario]):

    def find_by_id(self, id: int) -> Optional[Usuario]:
        return db.session.get(Usuario, id)

    def find_by_uuid(self, uuid: str) -> Optional[Usuario]:
        return Usuario.query.filter_by(uuid=uuid).first()

    def find_by_login(self, login: str) -> Optional[Usuario]:
        return Usuario.query.filter_by(user_login=login, status="ativo").first()

    def find_by_cpf_hash(self, cpf_hash: str) -> Optional[Usuario]:
        """Busca por HMAC-SHA256 do CPF (índice determinístico); ver nota em
        src/domains/paciente/repositories.py sobre por que não se pode
        buscar por igualdade do valor cifrado com AES-256-GCM."""
        return Usuario.query.filter_by(cpf_hash=cpf_hash).first()

    def find_by_email(self, email: str) -> Optional[Usuario]:
        return Usuario.query.filter_by(email=email).first()

    def find_by_tipo_papel(self, id_empresa: int, tipo_papel: str) -> List[Usuario]:
        """Substitui o antigo Usuario.query.filter_by(tipo_usuario=...).

        Faz o JOIN explícito com PapelProfissional, já que tipo_usuario
        não é mais coluna direta de Usuario.

        Parâmetros:
            id_empresa: filtra só usuários dessa empresa.
            tipo_papel: 'medico' ou 'enfermeiro' (não serve para 'admin',
                que não tem PapelProfissional -- usar find_admins abaixo).

        Retorno:
            Lista de instâncias de Usuario com papel ativo do tipo pedido.
        """
        return (
            Usuario.query
            .join(PapelProfissional, PapelProfissional.id_usuario == Usuario.id)
            .filter(
                Usuario.id_empresa == id_empresa,
                PapelProfissional.tipo_papel == tipo_papel,
                PapelProfissional.ativo == True,
            )
            .all()
        )

    def find_admins(self, id_empresa: int) -> List[Usuario]:
        """Lista usuários administradores de uma empresa (is_admin_flag)."""
        return Usuario.query.filter_by(id_empresa=id_empresa, is_admin_flag=True).all()

    def save(self, entity: Usuario, commit: bool = True) -> Usuario:
        if commit == True:
            db.session.add(entity)
            db.session.commit()
        else:
            db.session.add(entity)
            db.session.flush()
        return entity

    def save_sem_commit(self, entity):
        return entity

    def delete(self, id: int) -> bool:
        u = self.find_by_id(id)
        if not u:
            return False
        db.session.delete(u)
        db.session.commit()
        return True

    def find_all(self, id_empresa: int) -> List[Usuario]:
        return Usuario.query.filter_by(id_empresa=id_empresa).all()
    
     
    def find_all_param(self, id_empresa, offset: int = 0, especialidade: str = None, status: str = None, nome:str=None, email:str=None,cpf:str=None):
        filtros = {
            "id_empresa": id_empresa,
            "is_admin_flag": False
                  }

        if especialidade:
            filtros["especialidade"] = especialidade
        if status:
            filtros["status"] = status
        
        # TODO 
       # if cpf:
          #          filtros["cpf"] = cpf
             #   if email:
               #     filtros["email"] = email
        
        # if nome:
          #  Usuario.query.filter(Usuario.nome_completo.ilike(f"%{nome}%")).offset(offset).limit(8)
        
        
        return Usuario.query.filter_by(**filtros).offset(offset).limit(8)