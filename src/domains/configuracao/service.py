import copy

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError, BionException
from src.core.session import get_id_empresa_sessao
from .repository import ConfiguracaoRepository
from src.domains.configuracao.schema_config import validar_configuracoes
from src.models.usuarios import Configuracao, ConfiguracaoProtocolo
from src.domains.protocolo.shared.repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository


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

    ESCOPOS_VALIDOS = {"triagem", "consulta", "ambos"}

    def __init__(self):
        self.repo = ConfiguracaoRepository()
        self.repo_catalogo = ProtocoloCatalogoRepository()

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

            self._semear_favoritos_institucionais(cfg)

        return cfg

    def _semear_favoritos_institucionais(self, cfg):
        """Usuário novo já nasce com os defaults institucionais entre os favoritos
        (em_uso=True). NÃO preenche escopo_default pessoal: assim a cadeia de
        fallback continua viva e uma mudança futura do default da instituição
        vale para quem nunca escolheu o seu.
        Depende da sessão (empresa) -- só chamar dentro de uma requisição."""
        for vinculo in self.repo.find_vinculos_ativos_da_empresa(get_id_empresa_sessao()):
            if vinculo.escopo_default_institucional is None:
                continue
            self.repo.save_protocolo(ConfiguracaoProtocolo(
                id_configuracao=cfg.id,
                id_protocolo=vinculo.id_protocolo_catalogo,
                em_uso=True,
            ))

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
        catalogo = self.repo_catalogo.find_by_uuid(uuid_protocolo)
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
        id_protocolo = catalogo.id_protocolo_catalogo
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
        id_protocolo = catalogo.id_protocolo_catalogo
        id_empresa = get_id_empresa_sessao()

        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, id_protocolo)
        if not protocolo:
            raise RecursoNaoEncontradoError("Protocolo não configurado para este usuário.")

        vinculo_empresa = self.repo.find_empresa_protocolo(id_empresa, id_protocolo)
        if vinculo_empresa and vinculo_empresa.politica == "obrigatorio":
            raise ConflictoError("Este protocolo é obrigatório e não pode ser desativado.")
        # O default da instituição nunca some da lista do profissional: é o
        # protocolo que garante que ninguém fica sem opção (mesma regra que
        # impede a empresa de desativá-lo).
        if vinculo_empresa and vinculo_empresa.escopo_default_institucional is not None:
            raise ConflictoError("Este é o protocolo padrão da instituição e não pode ser desativado.")

        protocolo.em_uso = False
        # Convenção 3 do model: default pessoal só existe para protocolo em uso.
        # Pausado, libera o slot -- o escopo volta ao default da instituição.
        protocolo.escopo_default = None
        return self.repo.save_protocolo(protocolo)

    def definir_default_pessoal(self, id_usuario: int, uuid_protocolo: str, escopo: str):
        """Define o protocolo como default pessoal (carregado automático na consulta)
        para um escopo. Diferente do default institucional, que vive em EmpresaProtocolo."""
        if escopo not in self.ESCOPOS_VALIDOS:
            raise DadosInvalidosError(f"Escopo inválido: '{escopo}'. Valores aceitos: {sorted(self.ESCOPOS_VALIDOS)}.")

        catalogo = self._resolver_catalogo(uuid_protocolo)
        id_protocolo = catalogo.id_protocolo_catalogo

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
        """Tira o protocolo de default pessoal (escopo_default = NULL) sem pausá-lo.
        O escopo volta ao default da instituição -- ninguém fica sem padrão."""
        catalogo = self._resolver_catalogo(uuid_protocolo)
        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, catalogo.id_protocolo_catalogo)
        if not protocolo:
            raise RecursoNaoEncontradoError("Protocolo não configurado para este usuário.")
        protocolo.escopo_default = None
        return self.repo.save_protocolo(protocolo)

    def resolver_default(self, id_usuario: int, escopo: str):
        """Protocolo que a consulta deve carregar por padrão para o escopo.
        Devolve (ProtocoloCatalogo, origem). Cadeia, do mais específico ao mais geral:
          1. default pessoal do escopo (em uso e ainda liberado pela empresa)
          2. default pessoal "ambos" (se o escopo pedido não for "ambos")
          3. default institucional do escopo
          4. default institucional "ambos"
          5. primeiro protocolo liberado que sirva ao escopo (favoritos antes)
        Um protocolo "ambos" serve tanto a triagem quanto a consulta; por isso o
        slot "ambos" entra como fallback dos dois."""
        if escopo not in self.ESCOPOS_VALIDOS:
            raise DadosInvalidosError(f"Escopo inválido: '{escopo}'. Valores aceitos: {sorted(self.ESCOPOS_VALIDOS)}.")

        vinculos = {v.id_protocolo_catalogo: v
                    for v in self.repo.find_vinculos_ativos_da_empresa(get_id_empresa_sessao())}
        cfg = self.obter_ou_criar(id_usuario)
        # Só conta o que ainda está em uso E liberado: se a empresa desativou
        # depois, o default pessoal "cai" para o próximo da cadeia.
        em_uso = {p.id_protocolo: p for p in cfg.protocolos
                  if p.em_uso and p.id_protocolo in vinculos}
        escopos = [escopo] if escopo == "ambos" else [escopo, "ambos"]

        for esc in escopos:
            for p in em_uso.values():
                if p.escopo_default == esc:
                    return p.protocolo, "pessoal"

        for esc in escopos:
            for v in vinculos.values():
                if v.escopo_default_institucional == esc:
                    return v.protocolo_catalogo, "institucional"

        candidatos = sorted(
            (v for v in vinculos.values() if v.protocolo_catalogo.escopo_uso in escopos),
            key=lambda v: (v.id_protocolo_catalogo not in em_uso, v.id_protocolo_catalogo),
        )
        if not candidatos:
            raise RecursoNaoEncontradoError("Nenhum protocolo liberado para este escopo.")
        return candidatos[0].protocolo_catalogo, "primeiro_liberado"