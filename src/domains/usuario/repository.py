"""Repositorio de acesso a dados de Usuario.

find_by_tipo_papel() lista usuarios por funcao clinica (join com
PapelProfissional); find_admins() lista administradores (filtro por
is_admin). tipo_usuario nao existe como coluna nem property, entao
nenhum filtro aqui pode usa-lo.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy import or_
from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.usuarios import Usuario, CredencialWebAuthn
from src.models.usuarios.credencial_totp import CredencialTOTP
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
        """Lista usuários de uma empresa com papel ativo do tipo pedido.

        Parâmetros:
            id_empresa: filtra só usuários dessa empresa.
            tipo_papel: 'medico' ou 'enfermeiro' (não serve para 'admin',
                que não tem PapelProfissional -- usar find_admins abaixo).
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

    def find_senha_versao(self, id_usuario: int) -> Optional[int]:
        """Retorna só a coluna senha_versao do usuário, sem instanciar o
        Usuario inteiro -- usado por `requer_senha_atualizada`
        (session.py) nas rotas de leitura sensível que precisam
        comparar contra o valor gravado na sessão a cada requisição.
        Mais barato que find_by_id: 1 SELECT de uma coluna indexada por
        PK, sem carregar relacionamentos.

        Retorno: o inteiro, ou None se o usuário não existir mais
        (ex: deletado entre o login e esta requisição).
        """
        row = db.session.query(Usuario.senha_versao).filter_by(id=id_usuario).first()
        return row[0] if row else None

    def remover_credenciais(self, id_usuario: int, commit: bool = True) -> int:
        """Remove TODAS as credenciais WebAuthn de um usuário.

        Usado pelo reset de 2FA disparado por um super admin
        (UsuarioService.reset_2fa / reset_total). Diferente da
        autorremoção do próprio usuário (ver
        webauthn_2fa.remover_credencial), aqui NÃO existe a trava de
        "não pode remover a última" -- o objetivo desta operação é
        zerar o 2FA por completo, forçando o cadastro de um dispositivo
        novo no próximo login.

        Retorno:
            Quantidade de credenciais removidas.
        """
        apagadas = CredencialWebAuthn.query.filter_by(id_usuario=id_usuario).delete()
        apagadas += CredencialTOTP.query.filter_by(id_usuario=id_usuario).delete()
        
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return apagadas

    def save(self, entity: Usuario, commit: bool = True) -> Usuario:
        db.session.add(entity)
        if commit:
            db.session.commit()
        else:
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

    def find_all_param(self, id_empresa: int, offset: int = 0, especialidade: str = None, status: str = None, nome: str = None, email: str = None, cpf: str = None):
        filtros = {
            "id_empresa": id_empresa,
            "is_super_admin": 0
        }

        if especialidade:
            filtros["especialidade"] = especialidade
        if status:
            filtros["status"] = status

        # TODO: filtro por cpf, email e nome (nome via ilike, os demais
        # ainda não implementados)

        return Usuario.query.filter_by(**filtros).offset(offset).limit(8)

    def count_no_super_admin_users(self, id_empresa):
        return Usuario.query.where(Usuario.is_super_admin == False, Usuario.id_empresa == id_empresa).count()

    def count_status_users(self, id_empresa, status):
        return Usuario.query.where(Usuario.is_super_admin == False, Usuario.id_empresa == id_empresa, Usuario.status == status).count()

    def contar_ativos_por_papel(self, id_empresa: int) -> dict:
        """Contagem de usuários com status='ativo', agrupados por papel
        profissional (medico/enfermeiro), mais admins à parte.

        Diferente de find_by_tipo_papel (que retorna instâncias), este
        método já devolve a contagem agregada, sem carregar objetos
        Usuario inteiros na memória.

        Um mesmo usuário nunca é contado em duas categorias: um admin
        que também tem função clínica ativa (ex: dono de clínica que
        atende) conta só como "medico"/"enfermeiro", nunca como "admin"
        -- função clínica tem prioridade na contagem deste card. "admin"
        no resultado representa só quem é exclusivamente admin (sem
        papel clínico).

        Retorna dict, ex: {"medico": 12, "enfermeiro": 8, "admin": 2}
        """
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

    def find_inativos_ha_dias(self, id_empresa: int, dias: int = 7) -> List[Usuario]:
        """Usuários (não-super-admin) sem acesso há mais de N dias, ou que
        nunca acessaram (ultimo_acesso is None).
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

    def contar_inativos_ha_dias(self, id_empresa: int, dias: int = 7) -> int:
        """Conta usuários (não-super-admin, status ativo) sem acesso há mais de
        N dias, ou que nunca acessaram. Par de find_inativos_ha_dias
        (que retorna a lista completa), mais barato quando o card só
        precisa do total.
        """
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