"""
service.py

Regras de negócio do domínio Empresa. Orquestra o cadastro da empresa (sozinha
ou junto com o administrador fundador, na mesma transação), a atualização dos
dados autogerenciáveis e as consultas de existência de identificadores. Valida
a entrada pelos schemas, impede duplicidade de CNPJ e CNES, resolve a região
geográfica a partir do CEP e mantém o DPO sempre preenchido, usando o admin
fundador como padrão. CNPJ e CNES são identificadores, não colunas, e por isso
são gravados pelos métodos próprios do model; o CNPJ só é escrito na criação.
"""

import re

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError, BionException
from src.core.erros_pydantic import erros_pydantic_por_campo
from .repository import EmpresaRepository
from src.models.corp.empresa import Empresa
from .schema_empresa import CadastroEmpresaSchema, AtualizacaoEmpresaSchema
from src.models import db
from src.domains.usuario.services.service import UsuarioService
from .empresa_protocolo.empresa_protocolo_service import EmpresaProtocoloService

class EmpresaService:

    def __init__(self):
        self.repo = EmpresaRepository()
        self.usuario_service = UsuarioService()
        self.empresa_protocolo_service = EmpresaProtocoloService()

    def buscar_por_id(self, id_empresa: int) -> Empresa:
        """Retorna a empresa pelo id.

        Raises:
            RecursoNaoEncontradoError: empresa inexistente.
        """
        empresa = self.repo.find_by_id(id_empresa)
        if not empresa:
            raise RecursoNaoEncontradoError("Empresa não encontrada.")
        return empresa

    def _resolver_regiao(self, cep):
        """Busca a região geográfica pelo CEP. Sem CEP devolve None; CEP sem
        região correspondente levanta DadosInvalidosError no campo "cep"."""
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

    @staticmethod
    def _validar_cadastro(dados: dict) -> CadastroEmpresaSchema:
        """Valida o payload de cadastro; erros de validação viram DadosInvalidosError."""
        try:
            return CadastroEmpresaSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(
                erros_pydantic_por_campo(e),
                erros=erros_pydantic_por_campo(e, campo_geral="cnpj"),
            )

    def _garantir_identificadores_livres(self, schema: CadastroEmpresaSchema) -> None:
        """Levanta ConflictoError se o CNPJ ou o CNES informado já existir."""
        if schema.cnpj and self.repo.find_by_cnpj(schema.cnpj):
            raise ConflictoError("CNPJ já cadastrado.", campo="cnpj")
        if schema.cnes and self.repo.find_by_cnes(schema.cnes):
            raise ConflictoError("CNES já cadastrado.", campo="cnes")

    @staticmethod
    def _montar_empresa(schema: CadastroEmpresaSchema, regiao, dpo_nome, dpo_email) -> Empresa:
        """Instancia a empresa (sem salvar). CNPJ/CNES entram como identificadores."""
        empresa = Empresa(
            nome_fantasia=schema.nome_fantasia,
            razao_social=schema.razao_social,
            numero=schema.numero,
            bairro=schema.bairro,
            complemento=schema.complemento,
            cep=schema.cep,
            id_regiao_geografica=regiao.id if regiao else None,
            status_plano=schema.status_plano,
            plano=schema.plano,
            dpo_nome=dpo_nome,
            dpo_email=dpo_email,
        )
        if schema.cnpj:
            empresa.definir_cnpj(schema.cnpj)
        if schema.cnes:
            empresa.definir_cnes(schema.cnes)
        return empresa

    def cadastrar(self, dados: dict) -> Empresa:
        """Cadastra uma empresa sem administrador, com commit imediato.

        Raises:
            DadosInvalidosError: payload inválido ou CEP sem região.
            ConflictoError: CNPJ ou CNES já cadastrado.
        """
        schema = self._validar_cadastro(dados)
        self._garantir_identificadores_livres(schema)
        regiao = self._resolver_regiao(schema.cep)

        empresa = self._montar_empresa(schema, regiao, schema.dpo_nome, schema.dpo_email)
        return self.repo.save(empresa)

    def cadastrar_com_admin(self, dados_empresa: dict, dados_admin: dict) -> tuple:
        """Cadastra a empresa e o admin fundador (super admin) numa única transação.

        A região geográfica é resolvida pelo CEP. Se o DPO não for informado,
        usa nome e e-mail do admin criado (editável depois no PUT da empresa).
        Qualquer falha desfaz a transação inteira.

        Returns:
            (empresa, admin)

        Raises:
            DadosInvalidosError: payload inválido ou CEP sem região.
            ConflictoError: CNPJ ou CNES já cadastrado.
        """
        schema = self._validar_cadastro(dados_empresa)

        dados_admin = {**dados_admin, "is_admin": True}

        # Chaves conforme o model Usuario: nome_completo e email.
        dpo_nome = schema.dpo_nome or dados_admin.get("nome_completo")
        dpo_email = schema.dpo_email or dados_admin.get("email")

        self._garantir_identificadores_livres(schema)
        regiao = self._resolver_regiao(schema.cep)

        try:
            empresa = self._montar_empresa(schema, regiao, dpo_nome, dpo_email)
            self.repo.save(empresa, False)
            # empresa.id já existe aqui (flush interno do save com commit=False)

            admin = self.usuario_service.criar(empresa.id, dados_admin, False, is_super_admin=True)
            self.empresa_protocolo_service.liberar_todos_para_empresa(empresa.id, admin.id, commit=False)

            db.session.commit()
            return empresa, admin

        except Exception:
            db.session.rollback()
            raise

    def atualizar(self, id_empresa: int, dados: dict, uuid_empresa: str, commit: bool = True) -> Empresa:
        """Atualiza os campos autogerenciáveis da empresa (ver AtualizacaoEmpresaSchema).

        Args:
            id_empresa: id da empresa a atualizar (vem da sessão).
            dados: payload parcial; campos ausentes não são alterados.
            uuid_empresa: uuid da empresa da sessão; precisa bater com o da empresa carregada.
            commit: False só faz flush, deixando a transação aberta para o chamador.

        Regras: o CNPJ nunca é alterado aqui; CNES vazio significa "sem mudança";
        mudar o CEP recalcula a região geográfica; o DPO nunca fica nulo (se
        limpo de propósito ou já vazio, volta ao nome e e-mail do admin fundador).

        Raises:
            RecursoNaoEncontradoError: empresa inexistente.
            DadosInvalidosError: payload inválido ou CEP sem região.
            ConflictoError: CNES já pertence a outra empresa.
            BionException: uuid não corresponde à empresa informada.
        """
        empresa = self.buscar_por_id(id_empresa)

        if empresa.uuid != uuid_empresa:
            raise BionException("Não é possível alterar outras empresas.")

        try:
            schema = AtualizacaoEmpresaSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        atualizacoes = schema.model_dump(exclude_unset=True, exclude_none=True)

        # CEP novo: resolve a região antes de alterar qualquer coisa (pode levantar erro).
        nova_regiao = None
        novo_cep = atualizacoes.get("cep")
        if novo_cep and novo_cep != empresa.cep:
            nova_regiao = self._resolver_regiao(novo_cep)

        # CNES é property somente leitura no model: escrita via definir_cnes.
        novo_cnes = atualizacoes.pop("cnes", None)
        if novo_cnes and novo_cnes != empresa.cnes:
            outra = self.repo.find_by_cnes(novo_cnes)
            if outra and outra.id != empresa.id:
                raise ConflictoError("CNES já cadastrado.", campo="cnes")
            empresa.definir_cnes(novo_cnes)

        for campo, valor in atualizacoes.items():
            setattr(empresa, campo, valor)

        if nova_regiao:
            empresa.id_regiao_geografica = nova_regiao.id

        dono = next((u for u in empresa.usuarios if u.is_super_admin), None)
        if dono:
            for campo, atributo_dono in (("dpo_nome", "nome_completo"), ("dpo_email", "email")):
                limpou = campo in schema.model_fields_set and getattr(schema, campo) is None
                if limpou or not getattr(empresa, campo):
                    setattr(empresa, campo, getattr(dono, atributo_dono))

        return self.repo.save(empresa, commit=commit)

    @staticmethod
    def _exigir_somente_digitos(valor: str, campo: str) -> None:
        """CNPJ e CNES são gravados só com dígitos; valor com máscara ou outro
        caractere é bloqueado para evitar consulta enganosa (falso "não existe")."""
        if not re.fullmatch(r"[0-9]+", valor or ""):
            raise DadosInvalidosError(
                f"{campo.upper()} deve conter apenas números, sem pontos, barras ou traços.",
                campo=campo,
            )

    def cnpj_ja_cadastrado(self, cnpj: str) -> bool:
        """Raises:
            DadosInvalidosError: valor com caracteres que não são dígitos.
        """
        self._exigir_somente_digitos(cnpj, "cnpj")
        return self.repo.find_by_cnpj(cnpj) is not None

    def cnes_ja_cadastrado(self, cnes: str) -> bool:
        """Raises:
            DadosInvalidosError: valor com caracteres que não são dígitos.
        """
        self._exigir_somente_digitos(cnes, "cnes")
        return self.repo.find_by_cnes(cnes) is not None