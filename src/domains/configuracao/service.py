import json

from src.core.exceptions import RecursoNaoEncontradoError
from .repository import ConfiguracaoRepository


class ConfiguracaoService:

    CONFIGURACOES_DEFAULT = {
        "protocolos":{
            "mts": {
                "nome": "Manchester Triage System",
                "ativo": True,
                "criado_em": "",
                "codigo":""
                    },
            "news2":{
                "nome": "National Early Warning Score 2",
                "ativo": True,
                "criado_em": "",
            },
            "protocolo_personalizado": {
                "nome": "Protocolo Personalizado1",
                "ativo": False,
                "criado_em": "",
                "codigo": ""
            }
        },
        "design":{
            "tema": "claro",
            "tamanho_fonte": "medio",
            },
        "preferencias":{
            "linguagem": ["pt-BR"]
            }
    }
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
            cfg = Configuracao(id_usuario=id_usuario, configuracoes_json=json.dumps(self.CONFIGURACOES_DEFAULT))
            cfg = self.repo.save(cfg)
        return cfg

    def atualizar(self, id_usuario: int, configuracoes: dict):
        cfg = self.obter_ou_criar(id_usuario)
        atual = json.loads(cfg.configuracoes_json) if cfg.configuracoes_json else {}
        atual.update(configuracoes or {})
        cfg.configuracoes_json = atual
        return self.repo.save(cfg)

    
        