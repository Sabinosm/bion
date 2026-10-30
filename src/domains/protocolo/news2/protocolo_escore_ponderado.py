"""protocolo_escore_ponderado.py

Estratégia da família "escore-ponderado": protocolos cujo resultado vem da
soma de pontos de parâmetros isolados (NEWS2 hoje; qSOFA, Glasgow, Apgar no
futuro). Traduz a configuração cadastrada para o schema validado, valida as
respostas do front e calcula o escore, aplicando a regra de override e a
interpretação por faixas. O cálculo é puro e não acessa o banco.
"""
from pydantic import ValidationError

from ..shared.exceptions_protocolo import EstruturaInvalida
from ..shared.schemas.schema_resultado import PassoTrilha, SchemaResultado
from ..shared.strategy.base import CampoEsperado, ProtocoloStrategy
from ..shared.strategy.conversao_numerica import converter_numero
from .schema_protocolo_escore_config import (
    FaixaInterpretacao,
    FaixaPontuacao,
    ParametroEscore,
    RegraOverride,
    SchemaEscoreConfig,
)


class EscorePonderadoStrategy(ProtocoloStrategy):

    TIPO_PROTOCOLO = "escore-ponderado"

    def carregar_estrutura(self, dado_bruto) -> SchemaEscoreConfig:
        """Converte o model ProtocoloEscoreConfig no schema validado.

        Raises:
            EstruturaInvalida: se a configuração cadastrada não passar na validação do schema.
        """
        try:
            return SchemaEscoreConfig(
                schema_version=dado_bruto.schema_version,
                parametros=dado_bruto.parametros_json,
                regra_override=dado_bruto.regra_override_json,
                faixas_interpretacao=dado_bruto.faixas_interpretacao_json,
            )
        except ValidationError as ex:
            raise EstruturaInvalida(f"configuracao de escore invalida: {ex}") from ex

    def campos_esperados(self, estrutura: SchemaEscoreConfig) -> list[CampoEsperado]:
        return [
            CampoEsperado(
                campo=p.campo,
                texto=p.rotulo,
                tipo_campo=p.tipo_campo,
                opcoes=[{"valor": o.valor, "rotulo": o.rotulo} for o in p.opcoes] if p.tipo_campo == "enum" else None,
            )
            for p in estrutura.parametros
        ]

    def validar_respostas(self, estrutura: SchemaEscoreConfig, respostas: dict) -> dict:
        """Cruza as respostas do front com os parâmetros declarados.

        - chave desconhecida -> rejeita
        - numero: converte para número (int se inteiro, senão float) e exige que
          ele caiba em alguma faixa do parâmetro
        - enum: o valor precisa ser uma das opções declaradas
        - None / "" -> tratado como ausente (vira dados_ausentes em executar)

        Raises:
            ValueError: com todos os erros encontrados, separados por "; ".
        """
        por_campo = {p.campo: p for p in estrutura.parametros}
        erros: list[str] = []

        desconhecidas = sorted(set(respostas) - set(por_campo))
        if desconhecidas:
            erros.append(f"campos desconhecidos: {', '.join(desconhecidas)}")

        validados: dict = {}
        for campo, parametro in por_campo.items():
            bruto = respostas.get(campo)
            if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
                continue

            if parametro.tipo_campo == "numero":
                try:
                    numero = converter_numero(campo, bruto)
                except ValueError as ex:
                    erros.append(str(ex))
                    continue
                if self._faixa_do_valor(parametro, numero) is None:
                    erros.append(f"'{campo}': valor {numero} fora das faixas definidas para o parâmetro")
                    continue
                validados[campo] = numero
            else:
                valor = str(bruto)
                if valor not in {o.valor for o in parametro.opcoes}:
                    erros.append(f"'{campo}': '{valor}' não é uma opção válida")
                    continue
                validados[campo] = valor

        if erros:
            raise ValueError("; ".join(erros))
        return validados

    def executar(self, estrutura: SchemaEscoreConfig, dados_validados: dict) -> SchemaResultado:
        trilha: list[PassoTrilha] = []
        pontos_por_campo: dict[str, int] = {}
        dados_ausentes: list[str] = []

        for ordem, parametro in enumerate(estrutura.parametros, start=1):
            valor = dados_validados.get(parametro.campo)
            if valor is None:
                dados_ausentes.append(parametro.campo)
                continue

            pontos, valor_exibido = self._pontuar(valor, parametro)
            pontos_por_campo[parametro.campo] = pontos
            trilha.append(PassoTrilha(
                rotulo=parametro.rotulo,
                valor_observado=valor_exibido,
                peso_ou_resultado=f"{pontos} pontos",
                ordem=ordem,
            ))

        total = sum(pontos_por_campo.values())
        override_disparado = self._checar_override(pontos_por_campo, estrutura.regra_override)
        categoria, acao = self._classificar(total, override_disparado, estrutura.faixas_interpretacao)

        return SchemaResultado(
            classificacao=categoria,
            trilha_explicativa=trilha,
            dados_ausentes=dados_ausentes,
            metadata={
                "escore_total": total,
                "override_disparado": override_disparado,
                "acao_recomendada": acao,
                # com parâmetros faltando o total pode estar subestimado
                "escore_parcial": bool(dados_ausentes),
            },
        )

    @staticmethod
    def _pontuar(valor, parametro: ParametroEscore) -> tuple[int, str]:
        """Devolve (pontos, texto para a trilha). Ramifica por tipo_campo.

        Raises:
            EstruturaInvalida: se o valor não casar com nenhuma opção/faixa do parâmetro
                (não ocorre para respostas já passadas por `validar_respostas`).
        """
        if parametro.tipo_campo == "enum":
            for opcao in parametro.opcoes:
                if opcao.valor == valor:
                    return opcao.pontos, opcao.rotulo
            raise EstruturaInvalida(f"Valor '{valor}' não é uma opção válida de {parametro.campo}")

        faixa = EscorePonderadoStrategy._faixa_do_valor(parametro, valor)
        if faixa is None:
            raise EstruturaInvalida(f"Valor {valor} não se encaixa em nenhuma faixa de {parametro.campo}")
        return faixa.pontos, f"{valor} {parametro.unidade or ''}".strip()

    @staticmethod
    def _faixa_do_valor(parametro: ParametroEscore, valor: float) -> FaixaPontuacao | None:
        """Primeira faixa (limites inclusivos) que contém o valor, ou None se nenhuma contém."""
        for faixa in parametro.faixas:
            dentro_do_min = faixa.valor_min is None or valor >= faixa.valor_min
            dentro_do_max = faixa.valor_max is None or valor <= faixa.valor_max
            if dentro_do_min and dentro_do_max:
                return faixa
        return None

    @staticmethod
    def _checar_override(pontos_por_campo: dict[str, int], regra: RegraOverride | None) -> bool:
        """True se algum parâmetro isolado atingiu `pontos_minimos` (NEWS2: 3 pontos)."""
        if regra is None:
            return False
        return any(pontos >= regra.pontos_minimos for pontos in pontos_por_campo.values())

    @staticmethod
    def _classificar(
        total: int,
        override_disparado: bool,
        faixas: list[FaixaInterpretacao],
    ) -> tuple[str, str | None]:
        """Devolve (categoria, ação recomendada).

        A faixa marcada com `aplicada_por_override` só vale enquanto
        total <= escore_max dela (None = sempre). Acima disso, a faixa normal
        do total já é mais grave e prevalece: o override nunca rebaixa.

        Raises:
            EstruturaInvalida: se o total não se encaixar em nenhuma faixa.
        """
        if override_disparado:
            faixa_override = next((f for f in faixas if f.aplicada_por_override), None)
            if faixa_override and (faixa_override.escore_max is None or total <= faixa_override.escore_max):
                return faixa_override.categoria, faixa_override.acao_recomendada

        for faixa in faixas:
            if faixa.aplicada_por_override:
                continue
            dentro_do_min = faixa.escore_min is None or total >= faixa.escore_min
            dentro_do_max = faixa.escore_max is None or total <= faixa.escore_max
            if dentro_do_min and dentro_do_max:
                return faixa.categoria, faixa.acao_recomendada
        raise EstruturaInvalida(f"Escore total {total} não se encaixa em nenhuma faixa de interpretação")
