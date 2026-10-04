# news2/strategy/escore_ponderado.py

from ..shared.strategy.base import ProtocoloStrategy, CampoEsperado
from .schema_protocolo_escore_config import SchemaEscoreConfig, ParametroEscore
from ..shared.schemas.schema_resultado import SchemaResultado, PassoTrilha
import json


class EscorePonderadoStrategy(ProtocoloStrategy):

    def carregar_estrutura(self, dado_bruto) -> SchemaEscoreConfig:
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
            metadata={"escore_total": total, "override_disparado": override_disparado, "acao_recomendada": acao},
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