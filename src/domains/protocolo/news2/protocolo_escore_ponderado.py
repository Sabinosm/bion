# news2/strategy/escore_ponderado.py

from ..shared.strategy.base import ProtocoloStrategy, CampoEsperado
from .schema_protocolo_escore_config import (
    SchemaEscoreConfig,
    ParametroEscore,
    RegraOverride,
    FaixaInterpretacao,
)
from ..shared.schemas.schema_resultado import SchemaResultado, PassoTrilha


class EscorePonderadoStrategy(ProtocoloStrategy):

    def carregar_estrutura(self, dado_bruto) -> SchemaEscoreConfig:
        # db.JSON já devolve list/dict; o schema também aceita JSON em texto.
        return SchemaEscoreConfig(
            schema_version=dado_bruto.schema_version,
            parametros=dado_bruto.parametros_json,
            regra_override=dado_bruto.regra_override_json,
            faixas_interpretacao=dado_bruto.faixas_interpretacao_json,
        )

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
        - numero: converte para número (int se for inteiro, senão float)
        - enum: o valor precisa ser uma das opções declaradas
        - None / "" -> tratado como ausente (vira dados_ausentes em executar)
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
                if isinstance(bruto, bool):
                    erros.append(f"'{campo}': valor numérico inválido")
                    continue
                try:
                    numero = float(str(bruto).replace(",", ".")) if isinstance(bruto, str) else float(bruto)
                except ValueError:
                    erros.append(f"'{campo}': '{bruto}' não é um número")
                    continue
                if numero != numero or numero in (float("inf"), float("-inf")):
                    erros.append(f"'{campo}': valor numérico inválido")
                    continue
                validados[campo] = int(numero) if numero.is_integer() else numero
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

    def _pontuar(self, valor, parametro: ParametroEscore) -> tuple[int, str]:
        """Devolve (pontos, texto_para_trilha). Ramifica por tipo_campo."""
        if parametro.tipo_campo == "enum":
            for opcao in parametro.opcoes:
                if opcao.valor == valor:
                    return opcao.pontos, opcao.rotulo
            raise ValueError(f"Valor '{valor}' não é uma opção válida de {parametro.campo}")

        for faixa in parametro.faixas:
            dentro_do_min = faixa.valor_min is None or valor >= faixa.valor_min
            dentro_do_max = faixa.valor_max is None or valor <= faixa.valor_max
            if dentro_do_min and dentro_do_max:
                texto = f"{valor} {parametro.unidade or ''}".strip()
                return faixa.pontos, texto
        raise ValueError(f"Valor {valor} não se encaixa em nenhuma faixa de {parametro.campo}")

    def _checar_override(self, pontos_por_campo: dict[str, int], regra: RegraOverride | None) -> bool:
        """True se algum parâmetro isolado atingiu pontos_minimos (NEWS2: 3 pontos)."""
        if regra is None:
            return False
        return any(pontos >= regra.pontos_minimos for pontos in pontos_por_campo.values())

    def _classificar(
        self,
        total: int,
        override_disparado: bool,
        faixas: list[FaixaInterpretacao],
    ) -> tuple[str, str | None]:
        """Devolve (categoria, acao_recomendada).

        A faixa marcada com aplicada_por_override só vale enquanto
        total <= escore_max dela (None = sempre). Acima disso, a faixa normal
        do total já é mais grave e prevalece (o override nunca rebaixa).
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
        raise ValueError(f"Escore total {total} não se encaixa em nenhuma faixa de interpretação")