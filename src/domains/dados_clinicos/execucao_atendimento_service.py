"""Execução determinística de protocolo sobre o input VIGENTE do atendimento.

Guardas (nesta ordem): guard de escrita (404/409/403) -> só triagem/avaliação
médica -> binário completo -> catálogo ativo, escopo de uso compatível e
liberado pela empresa (EmpresaProtocolo.ativo é o único gate real) -> input
vigente (maior id) -> executa.

As respostas vêm de InputProtocolo.input_json, filtradas pelos campos que o
protocolo declara (chave de outro protocolo no mesmo input_json não derruba a
execução). Reexecutar o mesmo protocolo no mesmo input = 409 (UNIQUE); o
médico que ajusta as respostas cria outro input e executa de novo.

Ao fim, InputProtocolo.dados_criticos_ausentes_json é preenchido pelo sistema
com os dados ausentes consolidados de todas as execuções do input. Tudo em
uma transação.

RESOLVEDORES: tipo_protocolo -> callable(id_protocolo_catalogo, id_input,
respostas, executor, commit). Registre aqui o 'protocolo-composto'.
"""
import unicodedata

from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError
from src.domains.atendimento.contexto_clinico_service import ContextoClinicoService, AutorClinico
from src.domains.atendimento.binario.binario_gate import exigir_binario_completo
from src.domains.atendimento.repository import AtendimentoRepository
from .repository import InputProtocoloRepository
from .service import TIPOS_COM_INPUT_PROTOCOLO

ESCOPO_USO_POR_TIPO = {"triagem": "triagem", "avaliacao-medica": "consulta"}


def filtrar_respostas(input_json, campos: set) -> dict:
    """Só as chaves que o protocolo declara."""
    if not isinstance(input_json, dict):
        return {}
    # None/"" = nao respondido: fora do dict, vira dado ausente (o composto
    # rejeitaria None como valor invalido)
    return {k: v for k, v in input_json.items()
            if k in campos and v is not None and not (isinstance(v, str) and not v.strip())}


_VERDADEIRO = {"true", "sim", "s", "yes", "y", "1", "verdadeiro"}
_FALSO = {"false", "nao", "n", "no", "0", "falso"}


def traduzir_booleano(v):
    """bool, 'true'/'false', 'sim'/'nao' (sem acento, caixa livre), 1/0 -> bool.
    Qualquer outra coisa volta INTACTA: a validacao do protocolo rejeita (422)
    em vez de adivinharmos."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    if isinstance(v, str):
        t = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode().strip().lower()
        if t in _VERDADEIRO:
            return True
        if t in _FALSO:
            return False
    return v


def traduzir_respostas(respostas: dict, tipos: dict) -> dict:
    """Traduz so os campos declarados como booleano; o resto passa igual."""
    return {k: (traduzir_booleano(v) if tipos.get(k) == "booleano" else v)
            for k, v in respostas.items()}


def consolidar_ausentes(execucoes) -> list:
    """dados_ausentes únicos (ordem estável) de todas as execuções."""
    out = []
    for e in execucoes:
        for x in (e.dados_ausentes_json or []):
            nome = x if isinstance(x, str) else (x.get("campo") if isinstance(x, dict) else str(x))
            if nome not in out:
                out.append(nome)
    return out


def _resolver_escore(svc, id_cat, id_input, respostas, executor, commit):
    from src.domains.protocolo.news2.protocolo_escore_config_service import News2Service  # ajuste o caminho
    return News2Service().executar(id_cat, id_input, respostas, executor, commit=commit)


def _resolver_composto(svc, id_cat, id_input, respostas, executor, commit):
    from src.domains.protocolo.protocolo_composto.protocolo_composto_service import ProtocoloCompostoService  # ajuste
    return ProtocoloCompostoService().executar(id_cat, id_input, respostas, executor, commit=commit)




class ExecucaoAtendimentoService:

    RESOLVEDORES = {"escore-ponderado": _resolver_escore, "protocolo-composto": _resolver_composto}

    def __init__(self):
        from src.domains.protocolo.shared.repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository  # ajuste
        from src.domains.protocolo.shared.repositories.input_protocolo_execucao_repository import InputProtocoloExecucaoRepository  # ajuste
        from src.domains.empresa.empresa_protocolo.empresa_protocolo_repository import EmpresaProtocoloRepository
        self._ctx = ContextoClinicoService()
        self._at_repo = AtendimentoRepository()
        self._input_repo = InputProtocoloRepository()
        self._catalogo = ProtocoloCatalogoRepository()
        self._exec_repo = InputProtocoloExecucaoRepository()
        self._emp_prot = EmpresaProtocoloRepository()

    def executar(self, uuid_atendimento, uuid_paciente, uuid_protocolo, autor: AutorClinico):
        from src.domains.protocolo.shared.strategy.protocolo_factory import ProtocoloFactory  # ajuste

        ctx = self._ctx.exigir_escrita(uuid_atendimento, uuid_paciente, autor)
        at = ctx.atendimento
        if at.tipo_atendimento not in TIPOS_COM_INPUT_PROTOCOLO:
            raise ConflictoError("Execução de protocolo só existe em triagem ou avaliação médica "
                                 f"(este é '{at.tipo_atendimento}').")
        exigir_binario_completo(at)

        _, cat = self.exigir_protocolo_utilizavel(uuid_atendimento, uuid_protocolo, autor, autor.id_empresa)
        resolver = self.RESOLVEDORES.get(cat.tipo_protocolo)
        if not resolver:
            raise ConflictoError(f"Tipo de protocolo sem execução disponível: {cat.tipo_protocolo}.")

        inp = self._input_repo.find_ultimo_do_atendimento(at.id)
        if inp is None:
            raise ConflictoError("Registre o input de protocolo antes de executar.")

        strategy = ProtocoloFactory.obter(cat.tipo_protocolo)

        def respostas(estrutura, _strategy):
            esperados = strategy.campos_esperados(estrutura)
            filtradas = filtrar_respostas(inp.input_json, {c.campo for c in esperados})
            return traduzir_respostas(filtradas, {c.campo: c.tipo_campo for c in esperados})

        try:
            self._at_repo.travar(at)
            execucao = resolver(self, cat.id, inp.id, respostas, autor.id_usuario, False)
            inp.dados_criticos_ausentes_json = consolidar_ausentes(self._exec_repo.find_por_input(inp.id))
            self._input_repo.save(inp, commit=True)
            return execucao
        except Exception:
            self._input_repo.rollback()
            raise


    def exigir_atendimento(self, uuid_atendimento: str, id_empresa: int):
        """404 se o atendimento não existe (leitura; sem guard de escrita)."""
        at = self._at_repo.find_by_uuid(uuid_atendimento, id_empresa=id_empresa)
        if not at:
            raise RecursoNaoEncontradoError("Atendimento não encontrado.")
        return at

    def exigir_protocolo_utilizavel(self, uuid_atendimento, uuid_protocolo, autor, id_emp):
        """Atendimento + protocolo com os gates de uso (mesmos do executar):
        catálogo ativo, escopo compatível com o tipo de atendimento e
        liberado pela empresa (EmpresaProtocolo.ativo). Devolve (at, cat)."""
        at = self.exigir_atendimento(uuid_atendimento, id_emp)
        cat = self._catalogo.find_by_uuid(uuid_protocolo)
        if not cat:
            raise RecursoNaoEncontradoError(f"Protocolo não encontrado: {uuid_protocolo}")
        if cat.status != "ativo":
            raise ConflictoError("Este protocolo não está ativo.")
        if cat.escopo_uso not in (None, "ambos", ESCOPO_USO_POR_TIPO.get(at.tipo_atendimento)):
            raise ConflictoError("Este protocolo não se aplica a este tipo de atendimento.")
        vinculo = self._emp_prot.find_por_empresa_e_protocolo(autor.id_empresa, cat.id)
        if not vinculo or not vinculo.ativo:
            raise ConflictoError("Este protocolo não está liberado pela instituição.")
        return at, cat

    def listar_disponiveis(self, uuid_atendimento, autor, id_emp):
        """Catálogo que passa nos mesmos gates de uso, para o select do front."""
        at = self.exigir_atendimento(uuid_atendimento, id_emp)
        escopo = ESCOPO_USO_POR_TIPO.get(at.tipo_atendimento)
        candidatos = self._catalogo.find_ativos_para_escopo(escopo)
        liberados = {v.id_protocolo_catalogo
                     for v in self._emp_prot.find_ativos_por_empresa(autor.id_empresa)}
        return [c for c in candidatos if c.id in liberados]

    @staticmethod
    def _campo_dict(c):
        if hasattr(c, "to_dict"):
            return c.to_dict()
        if isinstance(c, dict):
            return c
        return {k: getattr(c, k) for k in ("campo", "label", "tipo_campo", "opcoes", "obrigatorio")
                if hasattr(c, k)}

    def estrutura_utilizavel(self, uuid_atendimento, uuid_protocolo, autor):
        """Campos esperados do protocolo (para montar o formulário do input)."""
        at, cat = self.exigir_protocolo_utilizavel(uuid_atendimento, uuid_protocolo, autor, autor.id_empresa)
        from src.domains.protocolo.shared.strategy.protocolo_factory import ProtocoloFactory  # ajuste
        versao = None
        if cat.versoes:
            versao = next((v for v in cat.versoes if getattr(v, "status", None) == "vigente"),
                          cat.versoes[-1])
        estrutura = getattr(versao, "estrutura_json", None) if versao else None
        strategy = ProtocoloFactory.obter(cat.tipo_protocolo)
        campos = strategy.campos_esperados(estrutura)
        return {
            "uuid": cat.uuid,
            "nome_protocolo": cat.nome_protocolo,
            "sigla": cat.sigla,
            "tipo_resultado": cat.tipo_resultado,
            "explicacao_json": cat.explicacao_json,
            "campos": [self._campo_dict(c) for c in campos],
        }