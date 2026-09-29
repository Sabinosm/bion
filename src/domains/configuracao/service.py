import copy

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError, BionException
from src.core.session import get_id_empresa_sessao
from .repository import ConfiguracaoRepository
from src.domains.configuracao.schema_config import validar_configuracoes
from src.models.usuarios import Configuracao, ConfiguracaoProtocolo


class ConfiguracaoService:

    # Protocolos (MTS, NEWS2, compostos) NÃO ficam no JSON de configuracoes.
    # Cada protocolo habilitado para o usuário vira uma linha em ConfiguracaoProtocolo,
    # restrita pela liberação institucional em EmpresaProtocolo (cascata de restrição:
    # o profissional só pode habilitar o que a empresa já liberou).
    #
    # Nas rotas de protocolo o identificador é o UUID do catálogo (o mesmo que a
    # página de catálogo já conhece); o id numérico fica só interno ao back.

    CONFIGURACOES_DEFAULT = {
        "design": {
            # "light", não "claro": tem que estar em TEMAS_PERMITIDOS (schema_config.py),
            # senão devolver o default num PUT seria rejeitado.
            "tema": "light",
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
                # deepcopy: dict() copiava só o nível de cima e os sub-dicts
                # ("design"/"preferencias") ficavam compartilhados com a constante
                # da classe -- qualquer mutação in-place vazaria entre usuários.
                configuracoes_json=copy.deepcopy(self.CONFIGURACOES_DEFAULT),
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

        # Merge por SEÇÃO: {"design": {"tema": "dark"}} troca só o tema e
        # preserva tamanho_fonte (o dict.update raso substituía "design"
        # inteiro). Listas (linguagem) são substituídas por completo -- é o
        # comportamento esperado para uma seleção.
        atual = copy.deepcopy(cfg.configuracoes_json) if cfg.configuracoes_json else {}
        for secao, valores in configuracoes_validadas.items():
            atual.setdefault(secao, {}).update(valores)

        cfg.configuracoes_json = atual  # novo objeto: o SQLAlchemy detecta a mudança no JSON
        return self.repo.save(cfg)

    # --- Protocolos ---

    def _resolver_catalogo(self, uuid_protocolo: str):
        catalogo = self.repo.find_catalogo_by_uuid(uuid_protocolo)
        if not catalogo:
            raise RecursoNaoEncontradoError("Protocolo não encontrado.")
        return catalogo

    def listar_protocolos(self, id_usuario: int):
        cfg = self.obter_ou_criar(id_usuario)
        return cfg.protocolos

    def habilitar_protocolo(self, id_usuario: int, uuid_protocolo: str):
        """Marca em_uso=True para o protocolo, respeitando a cascata de liberação:
        só é possível habilitar o que a empresa já liberou (EmpresaProtocolo.ativo=True).
        """
        catalogo = self._resolver_catalogo(uuid_protocolo)
        # ASSUNÇÃO 3: o model expõe a PK como `.id` (padrão dos outros models).
        id_protocolo = catalogo.id
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

    def desabilitar_protocolo(self, id_usuario: int, uuid_protocolo: str):
        """Marca em_uso=False. Bloqueado se a empresa tornou o protocolo obrigatório
        (EmpresaProtocolo.politica == 'obrigatorio') — a preferência existe, mas não
        pode ser desligada nesse caso."""
        catalogo = self._resolver_catalogo(uuid_protocolo)
        id_protocolo = catalogo.id
        id_empresa = get_id_empresa_sessao()

        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, id_protocolo)
        if not protocolo:
            raise RecursoNaoEncontradoError("Protocolo não configurado para este usuário.")

        vinculo_empresa = self.repo.find_empresa_protocolo(id_empresa, id_protocolo)
        if vinculo_empresa and vinculo_empresa.politica == "obrigatorio":
            raise ConflictoError("Este protocolo é obrigatório e não pode ser desativado.")

        protocolo.em_uso = False
        # Convenção 3 do model: default só existe para protocolo em uso.
        # Pausado, libera o slot em vez de deixar um default "fantasma".
        protocolo.escopo_default = None
        return self.repo.save_protocolo(protocolo)

    def definir_default_pessoal(self, id_usuario: int, uuid_protocolo: str, escopo: str):
        """Define o protocolo como default pessoal (carregado automático na consulta)
        para um escopo. Diferente do default institucional, que vive em EmpresaProtocolo."""
        if escopo not in self.ESCOPOS_VALIDOS:
            raise DadosInvalidosError(f"Escopo inválido: '{escopo}'. Valores aceitos: {sorted(self.ESCOPOS_VALIDOS)}.")

        catalogo = self._resolver_catalogo(uuid_protocolo)
        id_protocolo = catalogo.id

        # Convenção 3 do model: catálogo efetivo = liberado pela empresa + em_uso.
        vinculo_empresa = self.repo.find_empresa_protocolo(get_id_empresa_sessao(), id_protocolo)
        if not vinculo_empresa or not vinculo_empresa.ativo:
            raise DadosInvalidosError("Este protocolo não está liberado pela instituição.")

        # O protocolo precisa servir ao escopo pedido: um de triagem não vira
        # default de consulta, e "ambos" só vale para protocolos de uso "ambos".
        if catalogo.escopo_uso not in (escopo, "ambos"):
            raise DadosInvalidosError("Este protocolo não se aplica ao escopo escolhido.")

        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, id_protocolo)
        if not protocolo or not protocolo.em_uso:
            raise DadosInvalidosError("Só é possível definir como default um protocolo em uso.")

        # Libera o slot do escopo antes de ocupar de novo (uq_default_por_escopo).
        # commit=False: as duas escritas saem na MESMA transação (convenção 1 do
        # model) -- se a segunda falhar, o usuário não fica sem default nenhum.
        anterior = self.repo.find_default_do_escopo(cfg.id, escopo)
        if anterior and anterior.id_protocolo != id_protocolo:
            anterior.escopo_default = None
            self.repo.save_protocolo(anterior, commit=False)

        protocolo.escopo_default = escopo
        return self.repo.save_protocolo(protocolo)

    def remover_default_pessoal(self, id_usuario: int, uuid_protocolo: str):
        """Tira o protocolo de default (escopo_default = NULL) sem pausá-lo."""
        catalogo = self._resolver_catalogo(uuid_protocolo)
        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, catalogo.id)
        if not protocolo:
            raise RecursoNaoEncontradoError("Protocolo não configurado para este usuário.")
        protocolo.escopo_default = None
        return self.repo.save_protocolo(protocolo)