"""binario_service.py

Regras do binário: a conferência das quatro seções clínicas (alergias,
medicamentos, tipo sanguíneo e doença crônica) dentro de um Atendimento.

Não há tabela de estado: ele vive na coluna JSON `binario` do Atendimento, lida
e escrita pelo objeto Binario. Cada seção termina em um de três estados:
"preenchido" (o paciente tem o dado, com itens no payload ou com registro ativo
já existente, só confirmado), "nega" (o paciente não possui; com registro ativo
isso é impossível e dá 409) ou "nao-coletado" (não foi possível coletar).
Reconferir a mesma seção no mesmo atendimento dá 409.

A rota agregada e a granular usam o mesmo caminho por seção, chamando os
services públicos dos dados com commit desligado: um único commit no fim, ou
rollback de tudo se qualquer seção falhar. Como a conferência lê, altera e grava
um JSON, a linha do atendimento é TRAVADA (SELECT ... FOR UPDATE) antes da
gravação, para duas requisições simultâneas não se sobrescreverem.

Toda escrita passa pela checagem comum de escrita clínica (atendimento em
andamento do próprio profissional, mesmo paciente, etc.). A leitura exige só o
tenant. O gate "binário completo" vive em módulo próprio, sem dependência dos
services de paciente. Além da conferência, o serviço deriva o binário de um
atendimento novo a partir do paciente e reconcilia o do atendimento com os
registros ativos quando algum dado entra depois da conferência.
"""

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.erros_pydantic import erros_pydantic_por_campo
from src.domains.paciente.schemas.schema_tipo_sanguineo import ObservacaoTipoSanguineoCreateSchema
from src.domains.paciente.services.alergia_service import AlergiaService
from src.domains.paciente.services.doenca_cronica_service import DoencaCronicaService
from src.domains.paciente.services.medicamento_em_uso_service import MedicamentoEmUsoService
from src.domains.paciente.services.obs_tipo_sanguineo_service import ObservacaoTipoSanguineoService
from ..contexto_clinico_service import ContextoClinicoService, AutorClinico
from .schema_binario import BinarioIn, SCHEMA_POR_SECAO
from src.models.clinico.binario import Binario, SECOES_BINARIO, estado_de
from .binario_gate import exigir_binario_completo
from ..repository import AtendimentoRepository


class BinarioService:

    def __init__(self):
        self._ctx = ContextoClinicoService()
        self._atendimento_repo = AtendimentoRepository()
        self._alergia = AlergiaService()
        self._doenca = DoencaCronicaService()
        self._medicamento = MedicamentoEmUsoService()
        self._tipo = ObservacaoTipoSanguineoService()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _validar(schema, dados):
        """Valida `dados` com o schema Pydantic.

        Raises:
            DadosInvalidosError: corpo que não é objeto JSON, ou erros do schema por campo.
        """
        if not isinstance(dados, dict):
            raise DadosInvalidosError("Corpo da requisição inválido: esperado um objeto JSON.")
        try:
            return schema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError("Dados inválidos.", erros=erros_pydantic_por_campo(e))

    def _ativos(self, secao: str, uuid_paciente: str, id_empresa: int) -> list:
        """Registros ATIVOS da seção. Seção sem nenhum registro NÃO é erro: []."""
        try:
            if secao == "alergias":
                return list(self._alergia.listar_alergias(uuid_paciente, id_empresa))
            if secao == "doenca_cronica":
                return list(self._doenca.listar_doencas(uuid_paciente, id_empresa))
            if secao == "medicamentos":
                return list(self._medicamento.listar_medicamentos_em_uso(
                    uuid_paciente, id_empresa, apenas_ativos=True))
            vigente = self._tipo.tipo_vigente(uuid_paciente, id_empresa)
            return [vigente] if vigente else []
        except RecursoNaoEncontradoError:
            return []

    @staticmethod
    def _qtd_informada(secao: str, entrada) -> int:
        """Quantidade de itens informados na seção (tipo sanguíneo conta 0 ou 1)."""
        if secao == "tipo_sanguineo":
            return 1 if entrada.tipo_sanguineo else 0
        return len(entrada.itens)

    @staticmethod
    def _item(obj, uuid_atendimento: str) -> dict:
        """Item pré-preenchido + aviso de que veio de OUTRO momento e
        precisa de confirmação (sem origem conhecida = outro momento)."""
        d = obj.to_dict()
        origem = d.get("atendimento_origem_uuid") or d.get("uuid_atendimento_origem")
        d["de_outro_atendimento"] = origem != uuid_atendimento
        return d

    # ------------------------------------------------------------ leitura
    def estado(self, uuid_atendimento: str, id_empresa: int) -> dict:
        """Estado de conferência por seção. Seção pendente traz os registros
        ativos do paciente como pré-preenchimento (`de_outro_atendimento`
        indica o que precisa de confirmação visual)."""
        at = self._atendimento_repo.find_by_uuid(uuid_atendimento, id_empresa)
        if not at:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")
        paciente = at.consulta.paciente
        binario = Binario.de_atendimento(at)

        secoes = {}
        for s in SECOES_BINARIO:
            if binario.conferida(s):
                secoes[s] = binario.to_dict(s)
                continue
            itens = [self._item(o, at.uuid) for o in self._ativos(s, paciente.uuid, id_empresa)]
            secoes[s] = {
                "secao": s,
                "conferida": False,
                "estado": binario.estado(s) or "pendente",
                "possui": None,
                "pre_preenchido": itens,
                "precisa_confirmacao": any(i["de_outro_atendimento"] for i in itens),
            }
            revisao = binario.revisao(s)
            if revisao:
                # O front desmarca a seção e bloqueia o avanço até confirmar.
                secoes[s].update(origem="automatico", requer_revisao=True, **revisao)
        return {
            "uuid_atendimento": at.uuid,
            "completo": binario.completo,
            "pendentes": binario.pendentes,
            "secoes": secoes,
        }

    # ------------------------------------------- binário a partir do paciente
    @staticmethod
    def _entrada_alergia(a) -> dict:
        """Formato de AlergiaCreateSchema (uma reação: a mais recente ativa).
        `uuid`, `gravidade_maxima` e `reacoes` são só para exibição."""
        return {
            "uuid": a.uuid,
            "substancia": a.substancia,
            "codigo_substancia": a.codigo_substancia,
            "flag_confirmado": a.flag_confirmado,
            "tipo_reacao": a.tipo_reacao,
            "gravidade": a.gravidade,
            "descricao_reacao": a.descricao_reacao,
            # o schema de criação só comporta 1 reação; a maior gravidade e o
            # histórico ativo vão à parte para não se perderem na exibição
            "gravidade_maxima": a.gravidade_maxima,
            "reacoes": [r.to_dict() for r in a.reacoes_ativas],
        }

    @staticmethod
    def _entrada_doenca(d) -> dict:
        """Formato de DoencaCronicaCreateSchema."""
        return {
            "uuid": d.uuid,
            "codigo_cid10": d.codigo_cid10,
            "descricao_cid10": d.descricao_cid10,
            "desde": d.desde.isoformat() if d.desde else None,
            "status": d.status,
            "observacoes": d.observacoes,
        }

    @staticmethod
    def _entrada_medicamento(m) -> dict:
        """Formato de MedicamentoEmUsoCreateSchema."""
        cat = m.catalogo_medicamentos
        return {
            "uuid": m.uuid,
            "uuid_catalogo": cat.uuid if cat else None,
            "descricao": m.descricao,
            "dose": m.dose,
            "frequencia": m.frequencia,
            "desde": m.desde.isoformat() if m.desde else None,
        }

    _SERIALIZADOR = {
        "alergias": "_entrada_alergia",
        "doenca_cronica": "_entrada_doenca",
        "medicamentos": "_entrada_medicamento",
    }

    def binario_do_paciente(self, uuid_atendimento: str, id_empresa: int) -> dict:
        """Binário no formato do BinarioIn, montado a partir do PACIENTE.

        Registros ativos são a verdade. Seção sem registro ativo herda
        "nega"/"nao-coletado" da última conferência confirmada (atendimentos
        finalizados anteriores); sem histórico, fica pendente (possui=None).
        Só leitura: não grava nada."""
        at = self._atendimento_repo.find_by_uuid(uuid_atendimento, id_empresa)
        if not at:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")
        paciente = at.consulta.paciente
        anteriores = self._atendimento_repo.find_anteriores_do_paciente(
            paciente.id, at.id, id_empresa)

        binario, confirmacao, pendentes = {}, {}, []
        for s in SECOES_BINARIO:
            ativos = self._ativos(s, paciente.uuid, id_empresa)
            nao_coletado = False

            if ativos:
                possui = True
            else:
                ultimo = self._ultimo_estado_confirmado(s, anteriores)
                if ultimo == "nega" and s != "tipo_sanguineo":
                    possui = False
                elif ultimo == "nao-coletado":
                    possui, nao_coletado = False, True
                else:
                    possui = None

            if s == "tipo_sanguineo":
                valor = ativos[0].tipo_sanguineo if ativos else None
                binario[s] = {"possui": possui,
                              "nao_foi_possivel_coletar": nao_coletado,
                              "tipo_sanguineo": valor}
                corpo = dict(binario[s])
            else:
                ser = getattr(self, self._SERIALIZADOR[s])
                binario[s] = {"possui": possui,
                              "nao_foi_possivel_coletar": nao_coletado,
                              "itens": [ser(o) for o in ativos]}
                # confirmar o que já existe: SEM itens (evita duplicar registros)
                corpo = {"possui": possui, "nao_foi_possivel_coletar": nao_coletado, "itens": []}

            if possui is None:
                pendentes.append(s)
            else:
                confirmacao[s] = corpo

        return {
            "uuid_atendimento": at.uuid,
            "binario": binario,          # para exibir/editar (com itens)
            "confirmacao": confirmacao,  # seções resolvidas, prontas p/ POST sem duplicar
            "pendentes": pendentes,      # seções sem base: o profissional decide
            "completo": not pendentes,   # True => `confirmacao` serve na rota agregada
        }

    def exigir_binario_completo(self, atendimento) -> None:
        """Atalho para o gate do binário (409 se faltar seção)."""
        exigir_binario_completo(atendimento)

    def reconciliar(self, atendimento, id_empresa: int) -> list:
        """Alinha o binário DESTE atendimento com os registros ativos do paciente.

        Caso típico: o profissional conferiu "nega" e depois adicionou uma
        alergia pela rota granular. Seção "nega"/"nao-coletado" com registro
        ativo vira "preenchido" (marcada "reconciliado"). Não mexe em seção
        pendente nem em atendimento de outro momento.

        SEM commit (só flush): o chamador é dono da transação e deve ter
        TRAVADO o atendimento antes (repo.travar), pois lê e regrava o JSON.
        Devolve as seções alteradas."""
        paciente = atendimento.consulta.paciente
        binario = Binario.de_atendimento(atendimento)
        alteradas = []
        for s in SECOES_BINARIO:
            if not binario.conferida(s) or binario.estado(s) == "preenchido":
                continue
            ativos = self._ativos(s, paciente.uuid, id_empresa)
            if binario.reconciliar(s, bool(ativos)):
                alteradas.append(s)
        if alteradas:
            atendimento.binario = binario.para_json()
            self._atendimento_repo.save(atendimento, commit=False)
        return alteradas

    def derivar_na_abertura(self, atendimento, id_empresa: int) -> dict:
        """Deriva o binário de um atendimento NOVO a partir do paciente.

        Os registros ativos do paciente são a verdade (podem ter sido
        inseridos por outro profissional, fora de qualquer atendimento). Para
        cada seção, cruza-os com a ÚLTIMA conferência confirmada do paciente
        (atendimentos finalizados anteriores) conforme Binario.derivar:
        consistente -> repassa como "automatico"; mudou -> "requer-revisao"
        (conta como pendente, o profissional tem de confirmar).

        SEM commit (flush): chamado por AtendimentoService._criar, que é dono
        da transação. Devolve {secao: estado} do que foi gravado."""
        paciente = atendimento.consulta.paciente
        anteriores = self._atendimento_repo.find_anteriores_do_paciente(
            paciente.id, atendimento.id, id_empresa)
        binario = Binario.de_atendimento(atendimento)
        derivadas = {}
        for s in SECOES_BINARIO:
            if binario.estado(s) is not None:
                continue
            tem = bool(self._ativos(s, paciente.uuid, id_empresa))
            if binario.derivar(s, self._ultimo_estado_confirmado(s, anteriores), tem):
                derivadas[s] = binario.estado(s)
        if derivadas:
            atendimento.binario = binario.para_json()
            self._atendimento_repo.save(atendimento, commit=False)
        return derivadas

    @staticmethod
    def _ultimo_estado_confirmado(secao: str, anteriores: list):
        """Estado da seção na conferência mais recente (lista já em ordem
        decrescente). None = o paciente nunca teve a seção conferida."""
        for a in anteriores:
            b = Binario.de_atendimento(a)
            if b.conferida(secao):
                return b.estado(secao)
        return None

    # ------------------------------------------------------------ escrita
    def conferir_binario(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                         autor: AutorClinico) -> dict:
        """Rota agregada: as 4 seções de uma vez, atomicamente. Se qualquer
        seção já foi conferida (ex: por rota granular) -> 409 sem gravar nada."""
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = self._validar(BinarioIn, dados)
        pares = [(s, getattr(entrada, s)) for s in SECOES_BINARIO]
        resultados = self._gravar(ctx, pares, autor)
        return {"conferidas": resultados, "binario": self.estado(uuid_atendimento, autor.id_empresa)}

    def conferir_secao(self, secao: str, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                       autor: AutorClinico) -> dict:
        """Rota granular: uma seção. Mesmo caminho do agregado."""
        if secao not in SECOES_BINARIO:
            raise RecursoNaoEncontradoError(f"Seção do binário inexistente: {secao}")
        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        entrada = self._validar(SCHEMA_POR_SECAO[secao], dados)
        resultados = self._gravar(ctx, [(secao, entrada)], autor)
        return {"conferidas": resultados, "binario": self.estado(uuid_atendimento, autor.id_empresa)}

    def _gravar(self, ctx, pares, autor: AutorClinico) -> list:
        """UM commit para tudo; qualquer falha desfaz tudo. A linha do
        atendimento é travada ANTES de ler o JSON do binário."""
        repo = self._atendimento_repo
        try:
            at = repo.travar(ctx.atendimento)
            binario = Binario.de_atendimento(at)

            resultados = []
            for secao, entrada in pares:
                r = self._aplicar(secao, entrada, ctx, autor)
                binario.registrar(secao, r["estado"])
                resultados.append(r)

            at.binario = binario.para_json()
            repo.save(at, commit=False)
            repo.confirmar(commit=True)
            return resultados
        except IntegrityError as e:
            repo.rollback()
            raise ConflictoError(
                "Conflito ao gravar o binário (registro duplicado)."
            ) from e
        except Exception:
            repo.rollback()
            raise

    def _aplicar(self, secao: str, entrada, ctx, autor: AutorClinico) -> dict:
        """Uma seção, SEM commit (flush): cria os itens (se houver) e devolve o
        estado resultante. Não grava o binário, não comita e não faz rollback:
        quem chama (`_gravar`) é o dono da transação."""
        uuid_at, uuid_pac = ctx.atendimento.uuid, ctx.paciente.uuid
        possui, criados, alertas = None, 0, None

        if not entrada.nao_foi_possivel_coletar:
            possui = entrada.possui
            ativos = self._ativos(secao, uuid_pac, autor.id_empresa)
            if possui:
                if not ativos and self._qtd_informada(secao, entrada) == 0:
                    raise DadosInvalidosError(
                        "Dados inválidos.",
                        erros={secao: "possui=true exige ao menos um item ou um registro ativo já existente."},
                    )
                criados, alertas = self._criar_itens(secao, entrada, ativos, uuid_at, uuid_pac, autor)
            elif ativos:
                raise ConflictoError(
                    f"Seção '{secao}': o paciente tem registro ativo, então não pode ser conferida "
                    "como 'não possui'. Remova o registro (exclusão lógica) antes."
                )

        resultado = {"secao": secao, "estado": estado_de(possui), "itens_criados": criados}
        if alertas is not None:
            resultado["alertas_interacao"] = alertas
        return resultado

    def _criar_itens(self, secao, entrada, ativos, uuid_at, uuid_pac, autor):
        """Chama o service público de cada dado com commit=False (mesma
        validação e mesmo guard das rotas granulares do dado). Devolve
        (quantidade criada, alertas de interação ou None)."""
        if secao == "alergias":
            for item in entrada.itens:
                self._alergia.adicionar_alergia(uuid_at, uuid_pac, item, autor, commit=False)
            return len(entrada.itens), None

        if secao == "doenca_cronica":
            for item in entrada.itens:
                self._doenca.adicionar_doenca(uuid_at, uuid_pac, item, autor, commit=False)
            return len(entrada.itens), None

        if secao == "medicamentos":
            alertas = None
            for item in entrada.itens:
                _, alertas = self._medicamento.registrar(uuid_at, uuid_pac, item, autor, commit=False)
            return len(entrada.itens), alertas

        # tipo_sanguineo: só registra se informado e diferente do vigente
        # (igual ao vigente = apenas confirmação do que já está registrado).
        if not entrada.tipo_sanguineo:
            return 0, None
        normalizado = self._validar(
            ObservacaoTipoSanguineoCreateSchema, {"tipo_sanguineo": entrada.tipo_sanguineo}
        ).tipo_sanguineo
        vigente = ativos[0] if ativos else None
        if vigente is not None and vigente.tipo_sanguineo == normalizado:
            return 0, None
        self._tipo.registrar_tipo_sanguineo(
            uuid_at, uuid_pac, {"tipo_sanguineo": normalizado}, autor, commit=False)
        return 1, None
