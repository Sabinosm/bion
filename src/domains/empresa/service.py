"""
ALTERADO: Empresa(cnpj=...) não funciona mais no construtor (cnpj não
é mais coluna). Substituído por empresa.definir_cnpj(schema.cnpj) logo
após instanciar o objeto, nos dois pontos de criação
(cadastrar e cadastrar_com_admin).

atualizar(): o schema de atualização (AtualizacaoEmpresaSchema) bloqueia
CNPJ via "extra": "forbid" -- esse service nunca escreve CNPJ em uma
atualização, só na criação. O CNES, por outro lado, é editável: como é
um identificador (EmpresaIdentificador) e não coluna, é escrito com
empresa.definir_cnes() após checar duplicidade, e não via setattr.
"""

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError, BionException
from .repository import EmpresaRepository
from src.models.corp.empresa import Empresa
from .schema_empresa import CadastroEmpresaSchema, AtualizacaoEmpresaSchema, erros_pydantic_por_campo
from src.models import db
from src.domains.usuario.services.service import UsuarioService


class EmpresaService:

    def __init__(self):
        self.repo = EmpresaRepository()
        self.usuario_service = UsuarioService()

    def _resolver_regiao(self, cep):
        """Busca a região geográfica pelo CEP (usado nos dois fluxos de
        cadastro). Sem CEP, devolve None. CEP sem região correspondente
        levanta DadosInvalidosError no campo "cep"."""
        if not cep:
            return None
        try:
            from src.domains.regiao.cep_service import CepService
            return CepService().regiao_por_cep(cep)
        except RecursoNaoEncontradoError:
            raise DadosInvalidosError(
                f"Região geográfica não encontrada para cep: {cep}",
                campo="cep",
            )

    def cadastrar(self, dados: dict) -> "Empresa":
        try:
            schema = CadastroEmpresaSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(
                erros_pydantic_por_campo(e),
                erros=erros_pydantic_por_campo(e, campo_geral="cnpj"),
            )
        except Exception as e:
            raise

        if schema.cnpj and self.repo.find_by_cnpj(schema.cnpj):
            raise ConflictoError("CNPJ já cadastrado.", campo="cnpj")

        if schema.cnes and self.repo.find_by_cnes(schema.cnes):
            raise ConflictoError("CNES já cadastrado.", campo="cnes")

        regiao = self._resolver_regiao(schema.cep)

        empresa = Empresa(
            nome_fantasia=schema.nome_fantasia,
            razao_social=schema.razao_social,
            # cnpj REMOVIDO do construtor
            numero=schema.numero,
            bairro=schema.bairro,
            complemento=schema.complemento,
            cep=schema.cep,
            id_regiao_geografica=regiao.id if regiao else None,
            status_plano=schema.status_plano,
            plano=schema.plano,
            dpo_nome=schema.dpo_nome,
            dpo_email=schema.dpo_email,
        )
        if schema.cnpj:
            empresa.definir_cnpj(schema.cnpj)
        if schema.cnes:
            empresa.definir_cnes(schema.cnes)
        return self.repo.save(empresa)

    def cadastrar_com_admin(self, dados_empresa: dict, dados_admin: dict) -> tuple:
        """
        Cadastra uma empresa e um usuário admin associado a ela, em uma única transação.
        Validando dados de entrada e retornando erro caso não esteja de acordo.
        Também já adiciona à empresa o id_regiao através do cep, se não achar tenta procurar se já existe
        """
        
        try:
            schema_empresa = CadastroEmpresaSchema(**dados_empresa)
        except ValidationError as e:
            raise DadosInvalidosError(
                erros_pydantic_por_campo(e),
                erros=erros_pydantic_por_campo(e, campo_geral="cnpj"),
            )
        except Exception as e:
            raise

        dados_admin = {**dados_admin, "is_admin": True}

        # DPO é opcional no cadastro: se não informado, usa o nome e o e-mail
        # do admin que está sendo criado (editável depois em PUT /empresas/).
        # Chaves conforme o model Usuario: nome_completo e email.
        dpo_nome = schema_empresa.dpo_nome or dados_admin.get("nome_completo")
        dpo_email = schema_empresa.dpo_email or dados_admin.get("email")

        if schema_empresa.cnpj and self.repo.find_by_cnpj(schema_empresa.cnpj):
            raise ConflictoError("CNPJ já cadastrado.", campo="cnpj")

        if schema_empresa.cnes and self.repo.find_by_cnes(schema_empresa.cnes):
            raise ConflictoError("CNES já cadastrado.", campo="cnes")

        regiao = self._resolver_regiao(schema_empresa.cep)
        
        try:
            empresa = Empresa(
                nome_fantasia=schema_empresa.nome_fantasia,
                razao_social=schema_empresa.razao_social,
                numero=schema_empresa.numero,
                bairro=schema_empresa.bairro,
                complemento=schema_empresa.complemento,
                cep=schema_empresa.cep,
                id_regiao_geografica=regiao.id if regiao else None,
                status_plano=schema_empresa.status_plano,
                plano=schema_empresa.plano,
                dpo_nome=dpo_nome,
                dpo_email=dpo_email,
            )
            
            if schema_empresa.cnpj:
                empresa.definir_cnpj(schema_empresa.cnpj)
            if schema_empresa.cnes:
                empresa.definir_cnes(schema_empresa.cnes)
            self.repo.save(empresa, False)
            # empresa.id já existe aqui (flush interno do save com commit=False)

            admin = self.usuario_service.criar(empresa.id, dados_admin, False, is_super_admin=True)

            db.session.commit()
            return empresa, admin

        except Exception:
            db.session.rollback()
            raise

    def atualizar(self, id_empresa: int, dados: dict, uuid_empresa: str, commit: bool = True) -> Empresa:
        """Atualiza campos autogerenciáveis da empresa (ver
        AtualizacaoEmpresaSchema). CNPJ nunca é alterado aqui; CNES é
        tratado à parte por ser um identificador, não uma coluna."""

        empresa = self.repo.find_by_id(id_empresa)
        if not empresa:
            raise DadosInvalidosError("Empresa não encontrada.")

        if empresa.uuid != uuid_empresa:
            raise BionException("Não é possível alterar outras empresas.")

        try:
            schema = AtualizacaoEmpresaSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        atualizacoes = schema.model_dump(exclude_unset=True, exclude_none=True)

        # CNES: property somente leitura no model -> escrita via definir_cnes.
        # Vazio/None = "sem mudança" (não remove o CNES existente).
        novo_cnes = atualizacoes.pop("cnes", None)
        if novo_cnes and novo_cnes != empresa.cnes:
            outra = self.repo.find_by_cnes(novo_cnes)
            if outra and outra.id != empresa.id:
                raise ConflictoError("CNES já cadastrado.", campo="cnes")
            empresa.definir_cnes(novo_cnes)

        for campo, valor in atualizacoes.items():
            setattr(empresa, campo, valor)

        # DPO nunca fica nulo: se vier limpo de propósito (None/"" explícito)
        # ou se já estava vazio (empresas anteriores a este campo), volta ao
        # padrão -- nome e e-mail do admin fundador (super admin).
        dono = next((u for u in empresa.usuarios if u.is_super_admin), None)
        if dono:
            for campo, atributo_dono in (("dpo_nome", "nome_completo"), ("dpo_email", "email")):
                limpou = campo in schema.model_fields_set and getattr(schema, campo) is None
                if limpou or not getattr(empresa, campo):
                    setattr(empresa, campo, getattr(dono, atributo_dono))

        return self.repo.save(empresa, commit=commit)

    def cnpj_ja_cadastrado(self, cnpj: str) -> bool:
        """Verifica se o CNPJ já está cadastrado no sistema."""
        return self.repo.find_by_cnpj(cnpj) is not None

    def cnes_ja_cadastrado(self, cnes: str) -> bool:
        """Verifica se o CNES já está cadastrado no sistema."""
        return self.repo.find_by_cnes(cnes) is not None