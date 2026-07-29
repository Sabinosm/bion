"""
ALTERADO: Empresa(cnpj=...) não funciona mais no construtor (cnpj não
é mais coluna). Substituído por empresa.definir_cnpj(schema.cnpj) logo
após instanciar o objeto, nos dois pontos de criação
(cadastrar e cadastrar_com_admin).

atualizar() não precisou mudar: o schema de atualização (AtualizacaoEmpresaSchema)
já bloqueia alteração de CNPJ via "extra": "forbid" -- ou seja, esse
service nunca escreve CNPJ em uma atualização, só na criação.
"""

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError, BionException
from .repository import EmpresaRepository
from src.models.corp.empresa import Empresa
from ...schemas.schema_empresa import CadastroEmpresaSchema, AtualizacaoEmpresaSchema
from typing import Tuple
from src.models import db
from src.domains.usuario.services.service import UsuarioService


class EmpresaService:

    def __init__(self):
        self.repo = EmpresaRepository()
        self.usuario_service = UsuarioService()

    def cadastrar(self, dados: dict) -> "Empresa":
        try:
            schema = CadastroEmpresaSchema(**dados)
        except DadosInvalidosError:
            raise
        except Exception as e:
            raise DadosInvalidosError(f"Erro de validação: {e}") from e

        if self.repo.find_by_cnpj(schema.cnpj):
            raise ConflictoError("CNPJ já cadastrado.")

        empresa = Empresa(
            nome_fantasia=schema.nome_fantasia,
            razao_social=schema.razao_social,
            # cnpj REMOVIDO do construtor
            numero=schema.numero,
            bairro=schema.bairro,
            complemento=schema.complemento,
            cep=schema.cep,
            id_regiao_geografica=schema.id_regiao_geografica,
            status_plano=schema.status_plano,
            plano=schema.plano,
        )
        empresa.definir_cnpj(schema.cnpj)
        return self.repo.save(empresa)

    def cadastrar_com_admin(self, dados_empresa: dict, dados_admin: dict) -> tuple:
        """
        (Docstring de comportamento igual à versão anterior -- só a
        criação do CNPJ muda de argumento de construtor para chamada
        de método, ver comentário no bloco try abaixo.)
        """
        try:
            schema_empresa = CadastroEmpresaSchema(**dados_empresa)
        except Exception as e:
            raise DadosInvalidosError(f"Dados da empresa inválidos: {e}") from e

        dados_admin = {**dados_admin, "tipo_usuario": "admin"}

        if self.repo.find_by_cnpj(schema_empresa.cnpj):
            raise ConflictoError("CNPJ já cadastrado.")

        try:
            empresa = Empresa(
                nome_fantasia=schema_empresa.nome_fantasia,
                razao_social=schema_empresa.razao_social,
                # cnpj REMOVIDO do construtor
                numero=schema_empresa.numero,
                bairro=schema_empresa.bairro,
                complemento=schema_empresa.complemento,
                cep=schema_empresa.cep,
                id_regiao_geografica=schema_empresa.id_regiao_geografica,
                status_plano=schema_empresa.status_plano,
                plano=schema_empresa.plano,
            )
            empresa.definir_cnpj(schema_empresa.cnpj)
            self.repo.save(empresa, False)
            # empresa.id já existe aqui (flush interno do save com commit=False)

            admin = self.usuario_service.criar(empresa.id, dados_admin, False)

            db.session.commit()
            return empresa, admin

        except Exception:
            db.session.rollback()
            raise

    def atualizar(self, id_empresa: int, dados: dict, uuid_empresa: str) -> Empresa:
        """SEM MUDANÇA nesta função: AtualizacaoEmpresaSchema já bloqueia
        cnpj via extra='forbid', então este método nunca escreve CNPJ."""

        empresa = self.repo.find_by_id(id_empresa)

        if empresa.uuid == uuid_empresa:
            try:
                schema = AtualizacaoEmpresaSchema(**dados)
            except DadosInvalidosError:
                raise
            except Exception as e:
                raise DadosInvalidosError(f"Erro de validação: {e}") from e

            empresa = self.repo.find_by_id(id_empresa)
            if not empresa:
                raise DadosInvalidosError("Empresa não encontrada.")

            atualizacoes = schema.model_dump(exclude_unset=True, exclude_none=True)

            for campo, valor in atualizacoes.items():
                setattr(empresa, campo, valor)

            return self.repo.save(empresa)

        else:
            raise BionException(f"Não é possível alterar outras empresas:")