"""Strategy da família 'escore-ponderado'. Serve o NEWS2 hoje."""
from ...shared.strategy.base import ProtocoloStrategy, CampoEsperado
from ..schemas.schema_protocolo_escore_config import SchemaEscoreConfig, ParametroEscore
from ...shared.schemas.schema_resultado import SchemaResultado, PassoTrilha
import json


class ProtocoloEscorePonderadoStrategy(ProtocoloStrategy):

    def carregar_estrutura(self, dado_bruto) -> SchemaEscoreConfig:
        return SchemaEscoreConfig(
            schema_version=dado_bruto.schema_version,
            parametros=json.loads(dado_bruto.parametros_json),
            regra_override=json.loads(dado_bruto.regra_override_json) if dado_bruto.regra_override_json else None,
            faixas_interpretacao=json.loads(dado_bruto.faixas_interpretacao_json),
        )

    def campos_esperados(self, estrutura: SchemaEscoreConfig) -> list[CampoEsperado]:
        return [
            CampoEsperado(campo=p.campo, texto=p.rotulo, tipo_campo=p.tipo_campo)
            for p in estrutura.parametros
        ]

    def validar_respostas(self, estrutura: SchemaEscoreConfig, respostas: dict) -> dict:
        campos_validos = {p.campo for p in estrutura.parametros}
        chaves_desconhecidas = set(respostas.keys()) - campos_validos
        if chaves_desconhecidas:
            raise ValueError(f"Campos não pertencem a este protocolo: {chaves_desconhecidas}")
        # dado_ausente explícito (P-04): campo declarado mas não enviado
        return {campo: respostas.get(campo) for campo in campos_validos}

    def executar(self, estrutura: SchemaEscoreConfig, dados_validados: dict) -> SchemaResultado:
        trilha: list[PassoTrilha] = []
        pontos_por_campo: dict[str, int] = {}
        dados_ausentes: list[str] = []

        for ordem, parametro in enumerate(estrutura.parametros, start=1):
            valor = dados_validados.get(parametro.campo)
            if valor is None:
                dados_ausentes.append(parametro.campo)
                continue

            pontos = self._pontuar(valor, parametro)
            pontos_por_campo[parametro.campo] = pontos
            trilha.append(PassoTrilha(
                rotulo=parametro.rotulo,
                valor_observado=f"{valor} {parametro.unidade or ''}".strip(),
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
            },
        )

    def _pontuar(self, valor: float, parametro: ParametroEscore) -> int:
        for faixa in parametro.faixas:
            dentro_do_min = faixa.valor_min is None or valor >= faixa.valor_min
            dentro_do_max = faixa.valor_max is None or valor <= faixa.valor_max
            if dentro_do_min and dentro_do_max:
                return faixa.pontos
        raise ValueError(f"Valor {valor} não se encaixa em nenhuma faixa de {parametro.campo}")

    def _checar_override(self, pontos_por_campo: dict, regra) -> bool:
        if regra is None:
            return False
        if regra.condicao == "qualquer_parametro_score_3":
            return any(p == 3 for p in pontos_por_campo.values())
        return False

    def _classificar(self, total: int, override: bool, faixas) -> tuple[str, str]:
        if override:
            faixa_override = next((f for f in faixas if f.categoria == "alto"), faixas[-1])
            return faixa_override.categoria, faixa_override.acao_recomendada
        for faixa in faixas:
            if faixa.total_min <= total <= faixa.total_max:
                return faixa.categoria, faixa.acao_recomendada
        raise ValueError(f"Total {total} não se encaixa em nenhuma faixa de interpretação")