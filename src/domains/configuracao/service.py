from src.core.exceptions import RecursoNaoEncontradoError
from .repository import ConfiguracaoRepository
from src.database.usuarios import Configuracao, ConfiguracaoProtocolo


class ConfiguracaoService:

    # Protocolos (MTS, NEWS2, personalizados) NÃO ficam no JSON de configuracoes.
    # Cada protocolo habilitado para o usuário vira uma linha em
    # ConfiguracaoProtocolo, ligada a Configuracao por id_configuracao e ao
    # catálogo global de protocolos por id_protocolo.

    CONFIGURACOES_DEFAULT = {
        "design": {
            "tema": "claro",
            "tamanho_fonte": "medio",
        },
        "preferencias": {
            "linguagem": ["pt-BR"]
        }
    }

    # IDs de protocolo padrão a habilitar para todo usuário novo.
    # Ajustar para os IDs reais do catálogo (protocolo_catalogo).
    
    PROTOCOLOS_PADRAO_IDS: list = []

    def __init__(self):
        self.repo = ConfiguracaoRepository()

    def buscar_por_usuario(self, id_usuario: int):
        cfg = self.repo.find_by_usuario(id_usuario)
        if not cfg:
            raise RecursoNaoEncontradoError("Configuração não encontrada para este usuário.")
        return cfg

    def obter_ou_criar(self, id_usuario: int):
        cfg = self.repo.find_by_usuario(id_usuario)
        if not cfg:
            # configuracoes_json é db.JSON: atribuímos o dict direto,
            # sem json.dumps (o SQLAlchemy cuida da serialização).
            cfg = Configuracao(
                id_usuario=id_usuario,
                configuracoes_json=dict(self.CONFIGURACOES_DEFAULT),
            )
            cfg = self.repo.save(cfg)  # precisa existir (com PK) antes de criar as linhas filhas

            for id_protocolo in self.PROTOCOLOS_PADRAO_IDS:
                protocolo = ConfiguracaoProtocolo(
                    id_configuracao=cfg.id,
                    id_protocolo=id_protocolo,
                    ativo=True,
                )
                self.repo.save_protocolo(protocolo)

        return cfg

    def atualizar(self, id_usuario: int, configuracoes: dict):
        cfg = self.obter_ou_criar(id_usuario)
        atual = dict(cfg.configuracoes_json) if cfg.configuracoes_json else {}
        atual.update(configuracoes or {})
        cfg.configuracoes_json = atual
        return self.repo.save(cfg)

    # --- Protocolos ---

    def listar_protocolos(self, id_usuario: int):
        cfg = self.obter_ou_criar(id_usuario)
        return cfg.protocolos

    def habilitar_protocolo(self, id_usuario: int, id_protocolo: int, configuracoes: dict = None):
        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, id_protocolo)
        if not protocolo:
            protocolo = ConfiguracaoProtocolo(
                id_configuracao=cfg.id,
                id_protocolo=id_protocolo,
                ativo=True,
                configuracoes_json=configuracoes or {},
            )
        else:
            protocolo.ativo = True
            if configuracoes is not None:
                protocolo.configuracoes_json = configuracoes
        return self.repo.save_protocolo(protocolo)

    def desabilitar_protocolo(self, id_usuario: int, id_protocolo: int):
        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, id_protocolo)
        if not protocolo:
            raise RecursoNaoEncontradoError("Protocolo não configurado para este usuário.")
        protocolo.ativo = False
        return self.repo.save_protocolo(protocolo)