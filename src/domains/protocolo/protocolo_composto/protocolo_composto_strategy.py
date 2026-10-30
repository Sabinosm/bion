"""protocolo_composto_strategy.py

Estratégia da família "protocolo-composto": protocolos formados por vários
módulos (pontuadores, classificadores e regras/gatilhos) combinados por uma
regra de agregação. A estratégia não calcula por conta própria, apenas
orquestra: avalia os módulos-gatilho, aplica a regra de gatilho para desligar
módulos, avalia os demais, agrega por grupo e monta o contrato único de saída.

O cálculo é puro de ponta a ponta. A única etapa que lê Models é a de carregar
a estrutura, que os traduz para os tipos Pydantic do protocolo composto.
"""
from typing import Any

from pydantic import ValidationError

from src.core.exceptions import BionException
from ..shared.exceptions_protocolo import EstruturaInvalida
from ..shared.schemas.schema_resultado import PassoTrilha, SchemaResultado
from ..shared.strategy.base import CampoEsperado, ProtocoloStrategy
from ..shared.strategy.conversao_numerica import converter_numero
from .avaliadores import AVALIADORES
from .logic.agregacao_protocolo_composto import agregar
from .logic.gatilhos_protocolo_composto import aplicar_gatilhos
from .schemas.protocolo_composto_schemas import (
    CLASSIFICACAO_MULTIPLOS_RESULTADOS,
    EstruturaComposta,
    ModuloDef,
    ResultadoModulo,
    VariavelDef,
)

# tipo_dado da variável -> tipo_campo exposto ao front (mesmo vocabulário das demais famílias)
TIPO_CAMPO_POR_TIPO_DADO = {"numerico": "numero", "categorico": "enum", "booleano": "booleano"}


class ProtocoloCompostoStrategy(ProtocoloStrategy):

    TIPO_PROTOCOLO = "protocolo-composto"

    def carregar_estrutura(self, dado_bruto: Any) -> EstruturaComposta:
        """Traduz o envelope do repository para a estrutura Pydantic.

        `dado_bruto` é {"versao": ProtocoloVersao, "linhas": list[ProtocoloComposicao]
        (com módulo, versão do módulo, campos e variáveis já carregados), "config":
        ProtocoloComposicaoConfig | None}. Depois desta etapa nada mais toca o banco.

        Raises:
            EstruturaInvalida: sem módulos, sigla duplicada, variável com tipo
                divergente entre módulos ou composição que não passa na validação
                do schema.
        """
        linhas = dado_bruto.get("linhas") or []
        config = dado_bruto.get("config")
        versao = dado_bruto.get("versao")

        if not linhas:
            raise EstruturaInvalida("composicao sem nenhum modulo associado")

        variaveis: dict[str, VariavelDef] = {}
        try:
            modulos = [self._traduzir_modulo(linha, variaveis) for linha in linhas]

            siglas = [m.sigla for m in modulos]
            if len(siglas) != len(set(siglas)):
                raise EstruturaInvalida(f"sigla de modulo duplicada na composicao: {siglas}")

            return EstruturaComposta(
                modulos=modulos,
                variaveis=variaveis,
                agregacao=(config.agregacao if config else "nenhuma"),
                regra_gatilho=(config.regra_gatilho_json if config else None),
                codigo_composicao=getattr(versao, "codigo_composicao", None),
            )
        except ValidationError as ex:
            raise EstruturaInvalida(f"composicao cadastrada invalida: {ex}") from ex

    def campos_esperados(self, estrutura: EstruturaComposta) -> list[CampoEsperado]:
        """União das variáveis de todos os módulos, sem repetição."""
        return [
            CampoEsperado(
                campo=v.codigo,
                texto=v.nome,
                tipo_campo=TIPO_CAMPO_POR_TIPO_DADO[v.tipo_dado],
                opcoes=(
                    [{"valor": o["valor"], "rotulo": o.get("rotulo", o["valor"])} for o in v.opcoes]
                    if v.tipo_dado == "categorico" and v.opcoes else None
                ),
            )
            for v in estrutura.variaveis.values()
        ]

    def validar_respostas(self, estrutura: EstruturaComposta, respostas: dict) -> dict:
        """Valida as respostas contra o dicionário de variáveis (a união).

        Variável não enviada, `None` ou texto vazio não entra no resultado: é
        dado ausente, tratado pelos avaliadores e não erro aqui.

        Raises:
            ValueError: campo desconhecido ou valor inválido para o tipo da variável.
        """
        desconhecidas = set(respostas) - set(estrutura.variaveis)
        if desconhecidas:
            raise ValueError(f"campo(s) desconhecido(s): {sorted(desconhecidas)}")

        return {
            codigo: self._validar_valor(estrutura.variaveis[codigo], codigo, valor)
            for codigo, valor in respostas.items()
            if not (valor is None or (isinstance(valor, str) and not valor.strip()))
        }

    def executar(self, estrutura: EstruturaComposta, dados_validados: dict) -> SchemaResultado:
        resultados = self._avaliar_modulos(estrutura, dados_validados)
        classificacao, valor, grupos, excluidos = self._agregar(estrutura, resultados)
        trilha, ausentes = self._montar_trilha(estrutura, resultados)

        return SchemaResultado(
            classificacao=classificacao,
            trilha_explicativa=trilha,
            dados_ausentes=ausentes,
            metadata={
                "modulos": [r.model_dump() for r in resultados.values()],
                "alertas": self._montar_alertas(estrutura, resultados),
                "agregacao": {
                    "tipo": estrutura.agregacao,
                    "valor": valor,
                    "grupos": grupos,
                    "parcial": bool(excluidos),
                    "modulos_excluidos": excluidos,
                },
                "codigo_composicao": estrutura.codigo_composicao,
            },
        )

    # ------------------------------------------------------------------
    # carregar_estrutura
    # ------------------------------------------------------------------
    @staticmethod
    def _traduzir_modulo(linha, variaveis: dict[str, VariavelDef]) -> ModuloDef:
        """Traduz uma linha da composição em ModuloDef, acumulando em `variaveis`
        as variáveis dos campos do módulo (a união, sem duplicar)."""
        mv = linha.modulo_versao
        modulo_model = mv.modulo

        campos: list[tuple[str, bool]] = []
        for campo in mv.campos:
            var = campo.variavel
            campos.append((var.codigo, campo.obrigatorio))

            existente = variaveis.get(var.codigo)
            if existente is not None and existente.tipo_dado != var.tipo_dado:
                raise EstruturaInvalida(
                    f"variavel '{var.codigo}' declarada com tipo_dado "
                    f"divergente entre modulos ({existente.tipo_dado!r} "
                    f"vs {var.tipo_dado!r})"
                )
            variaveis[var.codigo] = VariavelDef(
                codigo=var.codigo,
                nome=var.nome,
                tipo_dado=var.tipo_dado,
                unidade=var.unidade,
                opcoes=var.opcoes_json,
                valor_min=float(var.valor_min) if var.valor_min is not None else None,
                valor_max=float(var.valor_max) if var.valor_max is not None else None,
            )

        return ModuloDef(
            sigla=modulo_model.sigla,
            versao=mv.numero_versao,
            familia=modulo_model.familia_calculo,
            tipo_saida=modulo_model.tipo_saida,
            papel=linha.papel,
            grupo_agregacao=linha.grupo_agregacao,
            configuracao=mv.configuracao_json,
            campos=campos,
        )

    # ------------------------------------------------------------------
    # validar_respostas
    # ------------------------------------------------------------------
    @staticmethod
    def _validar_valor(var: VariavelDef, codigo: str, valor: Any) -> Any:
        """Valida e normaliza uma resposta conforme o tipo_dado da variável."""
        if var.tipo_dado == "numerico":
            valor_num = float(converter_numero(codigo, valor))
            if var.valor_min is not None and valor_num < var.valor_min:
                raise ValueError(f"'{codigo}': {valor_num} abaixo do minimo ({var.valor_min})")
            if var.valor_max is not None and valor_num > var.valor_max:
                raise ValueError(f"'{codigo}': {valor_num} acima do maximo ({var.valor_max})")
            return valor_num

        if var.tipo_dado == "categorico":
            opcoes_validas = {o["valor"] for o in (var.opcoes or [])}
            if valor not in opcoes_validas:
                raise ValueError(f"'{codigo}': valor {valor!r} fora das opcoes {sorted(opcoes_validas)}")
            return valor

        if var.tipo_dado == "booleano":
            if not isinstance(valor, bool):
                raise ValueError(f"'{codigo}': esperado booleano, recebido {valor!r}")
            return valor

        # Defensivo: tipo_dado é um Literal fechado.
        raise ValueError(f"'{codigo}': tipo_dado desconhecido {var.tipo_dado!r}")  # pragma: no cover

    # ------------------------------------------------------------------
    # executar
    # ------------------------------------------------------------------
    def _avaliar_modulos(self, estrutura: EstruturaComposta, dados: dict) -> dict[str, ResultadoModulo]:
        """Avalia os gatilhos primeiro, aplica a regra de gatilho e avalia os demais
        módulos, marcando como não aplicáveis os desligados. A ordem do dict
        retornado é: gatilhos, depois os demais na ordem da composição."""
        resultados: dict[str, ResultadoModulo] = {}

        # Gatilhos são independentes entre si: cada um só olha os próprios campos.
        for m in estrutura.modulos:
            if m.papel == "gatilho":
                resultados[m.sigla] = self._avaliar_um(m, dados)

        desligados = aplicar_gatilhos(estrutura.regra_gatilho, resultados)

        for m in estrutura.modulos:
            if m.papel == "gatilho":
                continue
            if m.sigla in desligados:
                resultados[m.sigla] = ResultadoModulo(
                    sigla_modulo=m.sigla, versao=m.versao, status="nao_aplicavel",
                    tipo_saida=m.tipo_saida, motivo=desligados[m.sigla],
                )
            else:
                resultados[m.sigla] = self._avaliar_um(m, dados)

        return resultados

    @staticmethod
    def _agregar(
        estrutura: EstruturaComposta, resultados: dict[str, ResultadoModulo]
    ) -> tuple[str, Any, dict[str, Any], list[str]]:
        """Agrega os módulos de cada grupo. Devolve (classificacao, valor, grupos, excluidos).

        Só participam módulos com papel != 'gatilho' e grupo_agregacao preenchido,
        e o tipo de agregação do protocolo vale para todos os grupos. Com um único
        grupo, a classificação e o valor finais são os dele. Com mais de um, não há
        resultado combinado: a classificação é a convencional
        "multiplos-resultados" e cada grupo fica em `grupos`. Sem grupo ou com
        agregação "nenhuma", os módulos ficam em paralelo.
        """
        modulos_por_grupo: dict[str, list[str]] = {}
        for m in estrutura.modulos:
            if m.papel != "gatilho" and m.grupo_agregacao:
                modulos_por_grupo.setdefault(m.grupo_agregacao, []).append(m.sigla)

        if not modulos_por_grupo or estrutura.agregacao == "nenhuma":
            agregado = agregar("nenhuma", list(resultados.values()))
            return agregado.classificacao, None, {}, []

        agregados = {}
        excluidos: list[str] = []
        for grupo, siglas in modulos_por_grupo.items():
            agregado = agregar(estrutura.agregacao, [resultados[s] for s in siglas])
            agregados[grupo] = agregado
            if agregado.parcial:
                excluidos.extend(agregado.modulos_excluidos)

        if len(agregados) == 1:
            unico = next(iter(agregados.values()))
            classificacao, valor = unico.classificacao, unico.valor
        else:
            classificacao, valor = CLASSIFICACAO_MULTIPLOS_RESULTADOS, None

        grupos = {grupo: agregado.model_dump() for grupo, agregado in agregados.items()}
        return classificacao, valor, grupos, excluidos

    @staticmethod
    def _montar_trilha(
        estrutura: EstruturaComposta, resultados: dict[str, ResultadoModulo]
    ) -> tuple[list[PassoTrilha], list[str]]:
        """Concatena as trilhas dos módulos, renumerando a ordem, e une os dados
        ausentes (ordenados, sem repetição)."""
        trilha: list[PassoTrilha] = []
        ausentes: list[str] = []
        for m in estrutura.modulos:
            r = resultados[m.sigla]
            ausentes.extend(r.ausentes)
            for passo in r.trilha:
                trilha.append(PassoTrilha(
                    rotulo=passo.rotulo,
                    valor_observado=passo.valor_observado,
                    peso_ou_resultado=passo.contribuicao,
                    ordem=len(trilha),
                ))
        return trilha, sorted(set(ausentes))

    @staticmethod
    def _montar_alertas(estrutura: EstruturaComposta, resultados: dict[str, ResultadoModulo]) -> list[dict]:
        """Módulos (não gatilho) de saída "flag" calculados com valor verdadeiro."""
        alertas = []
        for m in estrutura.modulos:
            r = resultados[m.sigla]
            if m.papel != "gatilho" and r.tipo_saida == "flag" and r.status == "calculado" and r.valor is True:
                alertas.append({"modulo": r.sigla_modulo, "classificacao": r.classificacao, "motivo": r.motivo})
        return alertas

    @staticmethod
    def _avaliar_um(modulo: ModuloDef, dados: dict) -> ResultadoModulo:
        avaliador = AVALIADORES.get(modulo.familia)
        if avaliador is None:  # pragma: no cover - defensivo; familia é Literal fechado
            raise EstruturaInvalida(f"familia sem avaliador registrado: {modulo.familia!r}")
        try:
            return avaliador(modulo, dados)
        except BionException:
            raise  # já é um erro de configuração tratado (condição, etc.)
        except ValueError as ex:  # inclui o ValidationError do pydantic e `validar_configuracao`
            raise EstruturaInvalida(f"configuracao do modulo '{modulo.sigla}' invalida: {ex}") from ex
