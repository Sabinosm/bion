from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from .repository import EmpresaRepository


class EmpresaService:

    def __init__(self):
        self.repo = EmpresaRepository()

    def buscar_por_uuid(self, uuid: str):
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Empresa não encontrada: {uuid}")
        return e

    def listar(self):
        return self.repo.find_all()

    def criar(self, dados: dict):
        from src.database.corp import Empresa
        if not dados.get("nome_fantasia") or not dados.get("cnpj"):
            raise DadosInvalidosError("nome_fantasia e cnpj são obrigatórios.")
        if self.repo.find_by_cnpj(dados["cnpj"]):
            raise ConflictoError("CNPJ já cadastrado.")
        e = Empresa(
            nome_fantasia=dados["nome_fantasia"],
            razao_social=dados.get("razao_social"),
            cnpj=dados["cnpj"],
            numero=dados.get("numero"),
            bairro=dados.get("bairro"),
            complemento=dados.get("complemento"),
            cep=dados.get("cep"),
            id_regiao_geografica=dados.get("id_regiao_geografica"),
            status_plano=dados.get("status_plano", "ativo"),
            plano=dados.get("plano"),
        )
        return self.repo.save(e)

    def atualizar(self, uuid: str, dados: dict):
        e = self.buscar_por_uuid(uuid)
        for campo in ("nome_fantasia", "razao_social", "numero", "bairro",
                      "complemento", "cep", "status_plano", "plano"):
            if campo in dados:
                setattr(e, campo, dados[campo])
        return self.repo.save(e)
