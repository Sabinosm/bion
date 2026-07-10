from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError, BionException
from .repository import EmpresaRepository
from src.models.corp.empresa import Empresa
from ...schemas.schema_empresa import CadastroEmpresaSchema, AtualizacaoEmpresaSchema
from typing import Tuple
from src.models import db  # objeto de sessao/conexao (SQLAlchemy, etc)
from src.domains.usuario.service import UsuarioService


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
            cnpj=schema.cnpj,
            numero=schema.numero,
            bairro=schema.bairro,
            complemento=schema.complemento,
            cep=schema.cep,
            id_regiao_geografica=schema.id_regiao_geografica,
            status_plano=schema.status_plano,
            plano=schema.plano,
        )
        return self.repo.salvar(empresa)
 
    def cadastrar_com_admin(self, dados_empresa: dict, dados_admin: dict) -> tuple:
        """
        Cria a empresa e o usuário admin dela numa única transação
        atômica: se qualquer um dos dois falhar (CNPJ duplicado, CPF/
        email/login do admin duplicado, dados inválidos), NADA é
        persistido — a regra de "empresa nunca existe sem admin" nunca
        é violada, mesmo que o admin falhe depois da empresa já ter
        sido inserida na sessão.
 
        dados_admin não deve conter id_empresa (o schema de usuário nem
        aceita mais esse campo) — ele é sempre o id da empresa recém-criada,
        atribuído aqui dentro, nunca vindo do payload do cliente.
        """
        # 1. Validação de formato da empresa ANTES de abrir transação.
        try:
            schema_empresa = CadastroEmpresaSchema(**dados_empresa)
        except Exception as e:
            raise DadosInvalidosError(f"Dados da empresa inválidos: {e}") from e
 
        # tipo_usuario do admin é sempre fixo aqui, client não escolhe.
        dados_admin = {**dados_admin, "tipo_usuario": "admin"}
 
        # 2. Duplicidade do CNPJ checada cedo; duplicidade de CPF/email/
        #    login do admin é responsabilidade do UsuarioService.criar,
        #    então não duplicamos essa lógica aqui.
        if self.repo.find_by_cnpj(schema_empresa.cnpj):
            raise ConflictoError("CNPJ já cadastrado.")
 
        # 3. Transação atômica de verdade: usamos save_sem_commit nos dois
        #    repos, e só damos commit no final, depois que AMBOS os
        #    inserts (empresa + admin) já passaram por toda a validação.
        #    Se qualquer coisa falhar no meio, rollback() desfaz tudo —
        #    inclusive o insert da empresa que já tinha ido pro banco via
        #    flush(), porque flush() não fecha a transação, só o commit fecha.
        try:
            empresa = Empresa(
                nome_fantasia=schema_empresa.nome_fantasia,
                razao_social=schema_empresa.razao_social,
                cnpj=schema_empresa.cnpj,
                numero=schema_empresa.numero,
                bairro=schema_empresa.bairro,
                complemento=schema_empresa.complemento,
                cep=schema_empresa.cep,
                id_regiao_geografica=schema_empresa.id_regiao_geografica,
                status_plano=schema_empresa.status_plano,
                plano=schema_empresa.plano,
            )
            self.repo.save(empresa, False)
            # empresa.id já existe aqui — save(entity, False) já faz
            # add() + flush() internamente, sem fechar a transação.
 
            # id_empresa real, vindo do contexto (empresa recém-criada
            # dentro desta mesma transação), nunca do payload do cliente.
            admin = self.usuario_service.criar(empresa.id, dados_admin, False)
 
            db.session.commit()  # só aqui os dois inserts viram permanentes
            return empresa, admin
 
        except Exception:
            db.session.rollback()  # desfaz empresa E admin, mesmo que só um tenha falhado
            raise
 
    def atualizar(self, id_empresa: int, dados: dict, uuid_empresa: str) -> Empresa:
        
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
    
            # Se o CNPJ está sendo alterado, checa duplicidade ignorando a própria empresa
            if schema.cnpj and schema.cnpj != empresa.cnpj:
                existente = self.repo.find_by_cnpj(schema.cnpj)
                if existente and existente.id != id_empresa:
                    raise ConflictoError("CNPJ já cadastrado para outra empresa.")
    
            # model_dump com exclude_unset garante que só os campos enviados
            # pelo cliente sejam sobrescritos — campos ausentes no payload
            # permanecem com o valor atual da empresa.
            
            atualizacoes = schema.model_dump(exclude_unset=True, exclude_none=True)
            
            for campo, valor in atualizacoes.items():
                setattr(empresa, campo, valor)
 
            return self.repo.save(empresa)
        
        else:
            raise BionException (f"Não é possível alterar outras empresas:")
        
        