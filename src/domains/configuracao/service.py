from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError, BionException
from src.core.session import get_id_empresa_sessao
from .repository import ConfiguracaoRepository
from src.domains.configuracao.schema_config import validar_configuracoes
from src.models.usuarios import Configuracao, ConfiguracaoProtocolo


class ConfiguracaoService:

    # Protocolos (MTS, NEWS2, personalizados) NÃO ficam no JSON de configuracoes.
    # Cada protocolo habilitado para o usuário vira uma linha em ConfiguracaoProtocolo,
    # restrita pela liberação institucional em EmpresaProtocolo (cascata de restrição:
    # o profissional só pode habilitar o que a empresa já liberou).

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

    ESCOPOS_VALIDOS = {"triagem", "consulta", "ambos"}

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
            cfg = Configuracao(
                id_usuario=id_usuario,
                configuracoes_json=dict(self.CONFIGURACOES_DEFAULT),
            )
            cfg = self.repo.save(cfg)  # precisa existir (com PK) antes de criar as linhas filhas

            for id_protocolo in self.PROTOCOLOS_PADRAO_IDS:
                protocolo = ConfiguracaoProtocolo(
                    id_configuracao=cfg.id,
                    id_protocolo=id_protocolo,
                    em_uso=True,
                )
                self.repo.save_protocolo(protocolo)

        return cfg

    def atualizar(self, id_usuario: int, configuracoes: dict):
        try:
            configuracoes_validadas = validar_configuracoes(configuracoes)
        except ValueError as ex:
            raise BionException(str(ex), 400)

        cfg = self.obter_ou_criar(id_usuario)
        atual = dict(cfg.configuracoes_json) if cfg.configuracoes_json else {}
        atual.update(configuracoes_validadas)
        cfg.configuracoes_json = atual
        return self.repo.save(cfg)

    # --- Protocolos ---

    def listar_protocolos(self, id_usuario: int):
        cfg = self.obter_ou_criar(id_usuario)
        return cfg.protocolos

    def habilitar_protocolo(self, id_usuario: int, id_protocolo: int):
        """Marca em_uso=True para o protocolo, respeitando a cascata de liberação:
        só é possível habilitar o que a empresa já liberou (EmpresaProtocolo.ativo=True).
        """
        id_empresa = get_id_empresa_sessao()

        vinculo_empresa = self.repo.find_empresa_protocolo(id_empresa, id_protocolo)
        if not vinculo_empresa or not vinculo_empresa.ativo:
            raise DadosInvalidosError("Este protocolo não está liberado pela instituição.")

        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, id_protocolo)
        if not protocolo:
            protocolo = ConfiguracaoProtocolo(
                id_configuracao=cfg.id,
                id_protocolo=id_protocolo,
                em_uso=True,
            )
        else:
            protocolo.em_uso = True
        return self.repo.save_protocolo(protocolo)

    def desabilitar_protocolo(self, id_usuario: int, id_protocolo: int):
        """Marca em_uso=False. Bloqueado se a empresa tornou o protocolo obrigatório
        (EmpresaProtocolo.politica == 'obrigatorio') — a preferência existe, mas não
        pode ser desligada nesse caso."""
        id_empresa = get_id_empresa_sessao()

        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, id_protocolo)
        if not protocolo:
            raise RecursoNaoEncontradoError("Protocolo não configurado para este usuário.")

        vinculo_empresa = self.repo.find_empresa_protocolo(id_empresa, id_protocolo)
        if vinculo_empresa and vinculo_empresa.politica == "obrigatorio":
            raise ConflictoError("Este protocolo é obrigatório e não pode ser desativado.")

        protocolo.em_uso = False
        return self.repo.save_protocolo(protocolo)

    def definir_default_pessoal(self, id_usuario: int, id_protocolo: int, escopo: str):
        """Define o protocolo como default pessoal (carregado automático na consulta)
        para um escopo. Diferente do default institucional, que vive em EmpresaProtocolo."""
        if escopo not in self.ESCOPOS_VALIDOS:
            raise DadosInvalidosError(f"Escopo inválido: '{escopo}'. Valores aceitos: {sorted(self.ESCOPOS_VALIDOS)}.")

        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, id_protocolo)
        if not protocolo or not protocolo.em_uso:
            raise DadosInvalidosError("Só é possível definir como default um protocolo em uso.")

        # Libera o slot do escopo antes de ocupar de novo — a UNIQUE KEY
        # uq_default_por_escopo não permite dois defaults simultâneos no mesmo escopo.
        anterior = self.repo.find_default_do_escopo(cfg.id, escopo)
        if anterior and anterior.id_protocolo != id_protocolo:
            anterior.escopo_default = None
            self.repo.save_protocolo(anterior)

        protocolo.escopo_default = escopo
        return self.repo.save_protocolo(protocolo)