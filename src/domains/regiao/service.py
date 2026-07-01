from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .repository import RegiaoRepository


class RegiaoService:

    def __init__(self):
        self.repo = RegiaoRepository()

    def buscar_por_uuid(self, uuid: str):
        r = self.repo.find_by_uuid(uuid)
        if not r:
            raise RecursoNaoEncontradoError(f"Região geográfica não encontrada: {uuid}")
        return r

    def listar(self, tipo: str = None):
        if tipo:
            return self.repo.find_por_tipo(tipo)
        return self.repo.find_all()

    def criar(self, dados: dict):
        from src.database.corp import RegiaoGeografica
        if not dados.get("nome_regiao") or not dados.get("tipo_regiao"):
            raise DadosInvalidosError("nome_regiao e tipo_regiao são obrigatórios.")
        r = RegiaoGeografica(
            nome_regiao=dados["nome_regiao"],
            tipo_regiao=dados["tipo_regiao"],
            id_regiao_pai=dados.get("id_regiao_pai"),
            codigo_ibge=dados.get("codigo_ibge"),
            uf=dados.get("uf"),
            latitude_centroide=dados.get("latitude_centroide"),
            longitude_centroide=dados.get("longitude_centroide"),
            populacao_estimada=dados.get("populacao_estimada"),
        )
        return self.repo.save(r)
