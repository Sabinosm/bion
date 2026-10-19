"""
service.py

Regras de negócio do domínio Configuração: as preferências de cada usuário.
Elas têm duas naturezas separadas. A primeira é um JSON de aparência e idioma,
validado por schema e atualizado por merge parcial por seção. A segunda são os
protocolos clínicos habilitados pelo usuário, que NÃO ficam no JSON: cada um
vira uma linha própria, sempre restrita pela liberação institucional (o
profissional só habilita o que a empresa já liberou).

A configuração é criada sob demanda, no primeiro uso, já com os padrões
institucionais entre os favoritos do usuário. O protocolo padrão de cada
escopo (triagem, consulta ou ambos) segue uma cadeia do mais específico ao
mais geral: preferência pessoal, depois padrão da instituição, depois o
primeiro protocolo liberado.

Nas operações de protocolo o identificador é o UUID do catálogo (o mesmo que a
página de catálogo já conhece); o id numérico fica interno ao backend.
"""

import copy

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.session import get_id_empresa_sessao
from src.models.usuarios import Configuracao, ConfiguracaoProtocolo
from src.domains.protocolo.shared.repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository
from .repository import ConfiguracaoRepository
from .schema_config import validar_configuracoes


class ConfiguracaoService:

    CONFIGURACOES_DEFAULT = {
        "design": {
            # "light" (e não "claro"): precisa estar em TEMAS_PERMITIDOS
            # (schema_config.py), senão devolver o padrão num PUT seria rejeitado.
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

    # ------------------------------------------------------------------
    # Configuração do usuário
    # ------------------------------------------------------------------

    def buscar_por_usuario(self, id_usuario: int) -> Configuracao:
        """Configuração do usuário. Levanta RecursoNaoEncontradoError se ainda não existir."""
        cfg = self.repo.find_by_usuario(id_usuario)
        if not cfg:
            raise RecursoNaoEncontradoError("Configuração não encontrada para este usuário.")
        return cfg

    def obter_ou_criar(self, id_usuario: int) -> Configuracao:
        """Configuração do usuário, criada com os padrões no primeiro uso.

        Usuário sem configuração é tratado como exceção a corrigir: recebe os
        padrões na hora, em vez de falhar. A criação é "tudo ou nada": a
        configuração e os favoritos institucionais entram na mesma transação,
        então nunca sobra uma configuração sem os favoritos (que, já existindo,
        não seria semeada de novo). Se outra requisição criar a configuração
        primeiro, esta simplesmente usa a existente.

        Como a semeadura depende da empresa da sessão, só deve ser chamado
        dentro de uma requisição.
        """
        cfg = self.repo.find_by_usuario(id_usuario)
        if cfg:
            return cfg

        novo = Configuracao(
            id_usuario=id_usuario,
            # deepcopy: uma cópia rasa deixaria os sub-dicts ("design",
            # "preferencias") compartilhados com a constante da classe, e
            # qualquer mutação in-place vazaria entre usuários.
            configuracoes_json=copy.deepcopy(self.CONFIGURACOES_DEFAULT),
        )
        cfg, _ = self.repo.criar_com_favoritos(novo, self._favoritos_institucionais())
        return cfg

    def _favoritos_institucionais(self) -> list:
        """Ids dos protocolos padrão da instituição, que um usuário novo recebe como favoritos (em_uso=True).

        NÃO define o padrão pessoal (escopo_default): assim a cadeia de
        fallback continua viva, e uma mudança futura do padrão da instituição
        vale para quem nunca escolheu o seu.
        """
        return [
            vinculo.id_protocolo_catalogo
            for vinculo in self.repo.find_vinculos_ativos_da_empresa(get_id_empresa_sessao())
            if vinculo.escopo_default_institucional is not None
        ]

    def atualizar(self, id_usuario: int, configuracoes: dict) -> Configuracao:
        """Atualiza as configurações por merge parcial, validando o payload antes.

        O merge é por SEÇÃO: {"design": {"tema": "dark"}} troca só o tema e
        preserva `tamanho_fonte`. Listas (como `linguagem`) são substituídas
        por completo, que é o comportamento esperado de uma seleção.

        Args:
            id_usuario: id interno do usuário da sessão.
            configuracoes: conteúdo de `configuracoes` recebido do client.

        Raises:
            DadosInvalidosError: com a mensagem do schema, se o payload for inválido.
        """
        try:
            configuracoes_validadas = validar_configuracoes(configuracoes)
        except ValueError as ex:
            raise DadosInvalidosError(str(ex))

        cfg = self.obter_ou_criar(id_usuario)

        atual = copy.deepcopy(cfg.configuracoes_json) if cfg.configuracoes_json else {}
        for secao, valores in configuracoes_validadas.items():
            atual.setdefault(secao, {}).update(valores)

        # Objeto novo: é o que faz o SQLAlchemy detectar a mudança no JSON.
        cfg.configuracoes_json = atual
        return self.repo.save(cfg)

    # ------------------------------------------------------------------
    # Protocolos: validações compartilhadas
    # ------------------------------------------------------------------

    def _validar_escopo(self, escopo: str):
        if escopo not in self.ESCOPOS_VALIDOS:
            raise DadosInvalidosError(
                f"Escopo inválido: '{escopo}'. Valores aceitos: {sorted(self.ESCOPOS_VALIDOS)}."
            )

    def _resolver_catalogo(self, uuid_protocolo: str):
        catalogo = self.repo_catalogo.find_by_uuid(uuid_protocolo)
        if not catalogo:
            raise RecursoNaoEncontradoError("Protocolo não encontrado.")
        return catalogo

    def _exigir_liberado_pela_empresa(self, id_protocolo: int):
        """Garante que a empresa da sessão liberou o protocolo (EmpresaProtocolo.ativo=True) e devolve o vínculo."""
        vinculo = self.repo.find_empresa_protocolo(get_id_empresa_sessao(), id_protocolo)
        if not vinculo or not vinculo.ativo:
            raise DadosInvalidosError("Este protocolo não está liberado pela instituição.")
        return vinculo

    def _protocolo_configurado(self, cfg: Configuracao, id_protocolo: int) -> ConfiguracaoProtocolo:
        """Linha de preferência do usuário para o protocolo. Levanta RecursoNaoEncontradoError se não existir."""
        protocolo = self.repo.find_protocolo(cfg.id, id_protocolo)
        if not protocolo:
            raise RecursoNaoEncontradoError("Protocolo não configurado para este usuário.")
        return protocolo

    # ------------------------------------------------------------------
    # Protocolos: operações do usuário
    # ------------------------------------------------------------------

    def listar_protocolos(self, id_usuario: int) -> list:
        """Preferências de protocolo do usuário, só dos protocolos que a empresa mantém liberados.

        Um protocolo que a empresa desativou depois deixa de aparecer, como já
        deixa de valer na resolução do padrão; a linha do usuário é preservada
        e volta a aparecer se a empresa o liberar de novo. Cria a configuração
        se não existir.
        """
        cfg = self.obter_ou_criar(id_usuario)
        liberados = {
            v.id_protocolo_catalogo
            for v in self.repo.find_vinculos_ativos_da_empresa(get_id_empresa_sessao())
        }
        return [p for p in cfg.protocolos if p.id_protocolo in liberados]

    def habilitar_protocolo(self, id_usuario: int, uuid_protocolo: str) -> ConfiguracaoProtocolo:
        """Marca em_uso=True para o protocolo, respeitando a cascata de liberação.

        Só é possível habilitar o que a empresa já liberou.
        """
        catalogo = self._resolver_catalogo(uuid_protocolo)
        self._exigir_liberado_pela_empresa(catalogo.id)

        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, catalogo.id)
        if not protocolo:
            protocolo = ConfiguracaoProtocolo(
                id_configuracao=cfg.id,
                id_protocolo=catalogo.id,
                em_uso=True,
            )
        else:
            protocolo.em_uso = True
        return self.repo.save_protocolo(protocolo)

    def desabilitar_protocolo(self, id_usuario: int, uuid_protocolo: str) -> ConfiguracaoProtocolo:
        """Marca em_uso=False, liberando também o padrão pessoal do protocolo.

        Bloqueado (ConflictoError) se a empresa tornou o protocolo obrigatório
        (política "obrigatorio") ou se ele é o padrão da instituição, que nunca
        some da lista do profissional: é ele que garante que ninguém fica sem
        opção, a mesma regra que impede a empresa de desativá-lo.
        """
        catalogo = self._resolver_catalogo(uuid_protocolo)
        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self._protocolo_configurado(cfg, catalogo.id)

        vinculo_empresa = self.repo.find_empresa_protocolo(get_id_empresa_sessao(), catalogo.id)
        if vinculo_empresa and vinculo_empresa.politica == "obrigatorio":
            raise ConflictoError("Este protocolo é obrigatório e não pode ser desativado.")
        if vinculo_empresa and vinculo_empresa.escopo_default_institucional is not None:
            raise ConflictoError("Este é o protocolo padrão da instituição e não pode ser desativado.")

        protocolo.em_uso = False
        # O padrão pessoal só existe para protocolo em uso: pausado, libera o
        # slot, e o escopo volta ao padrão da instituição.
        protocolo.escopo_default = None
        return self.repo.save_protocolo(protocolo)

    def definir_default_pessoal(self, id_usuario: int, uuid_protocolo: str, escopo: str) -> ConfiguracaoProtocolo:
        """Define o protocolo como padrão pessoal de um escopo (carregado automático na consulta).

        Diferente do padrão institucional, que vive em EmpresaProtocolo.
        Exige que o protocolo seja liberado pela empresa, sirva ao escopo
        pedido (um de triagem não vira padrão de consulta, e "ambos" só vale
        para protocolos de uso "ambos") e esteja em uso.

        A troca do padrão anterior do escopo e a gravação do novo saem na mesma
        transação, para uma falha na segunda não deixar o usuário sem padrão
        nenhum.
        """
        self._validar_escopo(escopo)

        catalogo = self._resolver_catalogo(uuid_protocolo)
        self._exigir_liberado_pela_empresa(catalogo.id)

        if catalogo.escopo_uso not in (escopo, "ambos"):
            raise DadosInvalidosError("Este protocolo não se aplica ao escopo escolhido.")

        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self.repo.find_protocolo(cfg.id, catalogo.id)
        if not protocolo or not protocolo.em_uso:
            raise DadosInvalidosError("Só é possível definir como default um protocolo em uso.")

        # Libera o slot do escopo antes de ocupá-lo de novo (uq_default_por_escopo).
        anterior = self.repo.find_default_do_escopo(cfg.id, escopo)
        if anterior and anterior.id_protocolo != catalogo.id:
            anterior.escopo_default = None
            self.repo.save_protocolo(anterior, commit=False)

        protocolo.escopo_default = escopo
        return self.repo.save_protocolo(protocolo)

    def remover_default_pessoal(self, id_usuario: int, uuid_protocolo: str) -> ConfiguracaoProtocolo:
        """Tira o protocolo de padrão pessoal (escopo_default = NULL) sem pausá-lo.

        O escopo volta ao padrão da instituição: ninguém fica sem padrão.
        """
        catalogo = self._resolver_catalogo(uuid_protocolo)
        cfg = self.obter_ou_criar(id_usuario)
        protocolo = self._protocolo_configurado(cfg, catalogo.id)
        protocolo.escopo_default = None
        return self.repo.save_protocolo(protocolo)

    # ------------------------------------------------------------------
    # Protocolos: consultas
    # ------------------------------------------------------------------

    def mapa_estado_pessoal(self, id_usuario: int) -> dict:
        """{id_protocolo_catalogo: {"em_uso": bool, "escopo_default": str | None}}.

        Permite ao catálogo pintar a estrela de cada card numa única consulta.
        Somente leitura: não cria a configuração. Usuário sem configuração
        (exceção, corrigida pelos métodos que criam sob demanda) devolve {}.
        """
        cfg = self.repo.find_by_usuario(id_usuario)
        if not cfg:
            return {}
        return {
            p.id_protocolo: {"em_uso": p.em_uso, "escopo_default": p.escopo_default}
            for p in cfg.protocolos
        }

    def resolver_default(self, id_usuario: int, escopo: str):
        """Protocolo que a consulta deve carregar por padrão para o escopo.

        Cadeia, do mais específico ao mais geral:
          1. padrão pessoal do escopo (em uso e ainda liberado pela empresa)
          2. padrão pessoal "ambos" (se o escopo pedido não for "ambos")
          3. padrão institucional do escopo
          4. padrão institucional "ambos"
          5. primeiro protocolo liberado que sirva ao escopo (favoritos antes)

        Um protocolo "ambos" serve tanto à triagem quanto à consulta; por isso
        o slot "ambos" entra como fallback dos dois.

        Returns:
            (ProtocoloCatalogo, origem), com origem "pessoal", "institucional"
            ou "primeiro_liberado".

        Raises:
            DadosInvalidosError: escopo inválido.
            RecursoNaoEncontradoError: nenhum protocolo liberado serve ao escopo.
        """
        self._validar_escopo(escopo)

        vinculos = {v.id_protocolo_catalogo: v
                    for v in self.repo.find_vinculos_ativos_da_empresa(get_id_empresa_sessao())}
        cfg = self.obter_ou_criar(id_usuario)
        # Só conta o que ainda está em uso E liberado: se a empresa desativou
        # depois, o padrão pessoal "cai" para o próximo da cadeia.
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
