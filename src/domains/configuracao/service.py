from src.core.exceptions import RecursoNaoEncontradoError
from .repository import ConfiguracaoRepository


class ConfiguracaoService:

    def __init__(self):
        self.repo = ConfiguracaoRepository()

    def buscar_por_usuario(self, id_usuario: int):
        cfg = self.repo.find_by_usuario(id_usuario)
        if not cfg:
            raise RecursoNaoEncontradoError("Configuração não encontrada para este usuário.")
        return cfg

    def obter_ou_criar(self, id_usuario: int):
        from src.database.usuarios import Configuracao
        cfg = self.repo.find_by_usuario(id_usuario)
        if not cfg:
            cfg = Configuracao(id_usuario=id_usuario, configuracoes_json={})
            cfg = self.repo.save(cfg)
        return cfg

    def atualizar(self, id_usuario: int, configuracoes: dict):
        cfg = self.obter_ou_criar(id_usuario)
        atual = cfg.configuracoes_json or {}
        atual.update(configuracoes or {})
        cfg.configuracoes_json = atual
        return self.repo.save(cfg)
