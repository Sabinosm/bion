"""
ALTERADO: tipo_usuario deixou de existir por completo (nem coluna, nem
property) -- Usuario.query.filter_by(tipo_usuario=...) NÃO FUNCIONA.
Nenhum método aqui usava isso (find_all, find_by_login etc filtram por
outras colunas reais: is_admin, is_super_admin, status), então nada
quebrou de fato. find_by_tipo_papel() é o substituto para "listar por
função clínica" (join com PapelProfissional); find_admins() para
"listar administradores" (filtro por is_admin).

ALTERADO (separação admin/papel clínico, decisão confirmada):
- contar_ativos_por_papel(): um admin que também tem função clínica
  ativa (ex: dono de clínica que atende) agora conta SÓ na categoria
  da função clínica, nunca em "admin" -- evita contagem duplicada no
  card de estatística. Ver docstring do método.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy import or_
from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.usuarios import Usuario, CredencialWebAuthn
from src.models.usuarios.papel_profissional import PapelProfissional


class UsuarioRepository(IRepository[Usuario]):

    def find_by_id(self, id: int) -> Optional[Usuario]:
        return db.session.get(Usuario, id)

    def find_by_uuid(self, uuid: str) -> Optional[Usuario]:
        return Usuario.query.filter_by(uuid=uuid).first()

    def find_by_login(self, login: str) -> Optional[Usuario]:
        return Usuario.query.filter(
    Usuario.user_login == login,
        or_(Usuario.status == "ativo", Usuario.status == "pendente"),
    ).first()

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
        """Lista usuários administradores de uma empresa (is_admin)."""
        return Usuario.query.filter_by(id_empresa=id_empresa, is_admin=True).all()

    def remover_credenciais_webauthn(self, id_usuario: int) -> int:
        """Remove TODAS as credenciais WebAuthn de um usuário.

        Usado pelo reset de 2FA disparado por um super admin
        (UsuarioService.reset_2fa / reset_total). Diferente da
        autorremoção do próprio usuário (ver
        webauthn_2fa.remover_credencial), aqui NÃO existe a trava de
        "não pode remover a última" -- o objetivo explícito desta
        operação é zerar o 2FA por completo, forçando o usuário a
        cadastrar um dispositivo novo no próximo login.

        Retorno:
            Quantidade de credenciais removidas.
        """
        apagadas = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).delete()
        db.session.commit()
        return apagadas

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
    
     
    def find_all_param(self, id_empresa:int, offset: int = 0, especialidade: str = None, status: str = None, nome:str=None, email:str=None,cpf:str=None):
        filtros = {
            "id_empresa": id_empresa,
            "is_super_admin": 0
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
    
    def count_no_super_admin_users(self, id_empresa):
        return Usuario.query.where(Usuario.is_super_admin==False, Usuario.id_empresa==id_empresa).count()
        

    def count_status_users(self,id_empresa,status):
        return Usuario.query.where(Usuario.is_super_admin==False, Usuario.id_empresa==id_empresa,Usuario.status==status).count()
        
    # --- A4: Efetivo ativo por papel ---
    def contar_ativos_por_papel(self, id_empresa: int) -> dict:
        """Contagem de usuários com status='ativo', agrupados por papel
        profissional (medico/enfermeiro), mais admins à parte.

        Diferente de find_by_tipo_papel (que retorna instâncias), este
        método já devolve a contagem agregada -- é o que a estatística
        precisa, sem carregar objetos Usuario inteiros na memória.

        DECISÃO (separação admin/papel clínico, confirmada): um mesmo
        usuário nunca é contado em duas categorias. Um admin que também
        tem função clínica ativa (ex: dono de clínica que atende) conta
        SÓ como "medico"/"enfermeiro" aqui, nunca como "admin" -- função
        clínica tem prioridade na contagem deste card, mesmo que
        is_admin=True. "admin" no resultado representa só quem é
        exclusivamente admin (sem papel clínico).

        Retorna dict, ex: {"medico": 12, "enfermeiro": 8, "admin": 2}
        """
        from src.models.usuarios.papel_profissional import PapelProfissional

        # Profissionais (médico/enfermeiro) via PapelProfissional ativo.
        # Inclui quem também é admin -- prioridade da função clínica na
        # contagem, por decisão confirmada.
        linhas = (
            db.session.query(
                PapelProfissional.tipo_papel.label("tipo_papel"),
                func.count(Usuario.id).label("total"),
            )
            .join(Usuario, PapelProfissional.id_usuario == Usuario.id)
            .filter(
                Usuario.id_empresa == id_empresa,
                Usuario.status == "ativo",
                PapelProfissional.ativo == True,
            )
            .group_by(PapelProfissional.tipo_papel)
            .all()
        )
        resultado = {linha.tipo_papel: linha.total for linha in linhas}

        # ALTERADO: "admin" agora conta só quem é EXCLUSIVAMENTE admin
        # (sem PapelProfissional ativo) -- antes de nascer a
        # possibilidade de admin-médico, todo is_admin=True já era
        # implicitamente exclusivo, então este filtro extra não mudava
        # nada; agora evita contar a mesma pessoa em duas categorias.
        total_admins = (
            Usuario.query
            .outerjoin(
                PapelProfissional,
                (PapelProfissional.id_usuario == Usuario.id) & (PapelProfissional.ativo == True),
            )
            .filter(
                Usuario.id_empresa == id_empresa,
                Usuario.status == "ativo",
                Usuario.is_super_admin == False,
                Usuario.is_admin == True,
                PapelProfissional.id.is_(None),  # sem papel clínico ativo
            )
            .count()
        )
        if total_admins:
            resultado["admin"] = total_admins

        return resultado

    # --- A5 (fase futura): Engajamento/atividade da equipe ---
    def find_inativos_ha_dias(self, id_empresa: int, dias: int = 7) -> List[Usuario]:
        """Usuários (não-super-admin) sem acesso há mais de N dias, ou que
        nunca acessaram (ultimo_acesso is None). Já deixo pronto porque
        é praticamente 'de graça' junto com A4, mas A5 em si é fase 1
        'nice to have' -- confirmar com o time se entra agora.
        """
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        return (
            Usuario.query
            .filter(
                Usuario.id_empresa == id_empresa,
                Usuario.status == "ativo",
                Usuario.is_super_admin == False,
                db.or_(Usuario.ultimo_acesso < limite, Usuario.ultimo_acesso.is_(None)),
            )
            .all()
        )
        
# --- A5: Engajamento/atividade da equipe (contagem) ---
    def contar_inativos_ha_dias(self, id_empresa: int, dias: int = 7) -> int:
        """Conta usuários (não-super-admin, status ativo) sem acesso há mais de
        N dias, ou que nunca acessaram. Par de find_inativos_ha_dias
        (que retorna a lista completa) -- este devolve só o número, mais
        barato quando o card só precisa do total.
        """
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import or_

        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        return (
            Usuario.query
            .filter(
                Usuario.id_empresa == id_empresa,
                Usuario.status == "ativo",
                Usuario.is_super_admin == False,
                or_(Usuario.ultimo_acesso < limite, Usuario.ultimo_acesso.is_(None)),
            )
            .count()
        )