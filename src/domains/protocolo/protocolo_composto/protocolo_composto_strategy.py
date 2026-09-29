"""ProtocoloCompostoStrategy: a Strategy de 'tipo_protocolo=protocolo-composto'.

Nao calcula nada por conta propria -- so orquestra:
  1. avalia modulos-gatilho primeiro
  2. aplica regra_gatilho_json (logic/gatilhos.py) -> marca desligados
  3. avalia os demais modulos (avaliadores/*), pulando os desligados
  4. agrega por grupo (logic/agregacao.py)
  5. monta o SchemaResultado (contrato unico, shared/schemas/schema_resultado.py)

Funcao pura de ponta a ponta a partir de `executar()`: nenhuma chamada a
banco aqui. `carregar_estrutura()` e o unico ponto que le Models, e so
traduz para os tipos Pydantic de `schemas.py`.

NOTA DE INTEGRACAO (nomes de import a ajustar pelo usuario para a pasta
`logic/` que ele decidiu criar): aqui uso os caminhos como estao na minha
arvore local (`.condicao`, `.agregacao`, `.gatilhos`) -- trocar para
`.logic.condicao`, `.logic.agregacao`, `.logic.gatilhos` (ou o que for
escolhido) na hora de integrar.
"""
from typing import Any

from .logic.agregacao_protocolo_composto import AgregacaoInvalida, agregar
from .avaliadores import AVALIADORES
from .logic.gatilhos_protocolo_composto import GatilhoInvalido, aplicar_gatilhos
from .schemas.protocolo_composto_schemas import EstruturaComposta, ModuloDef, ResultadoModulo, VariavelDef

# Import do projeto real (fora deste pacote): interface e contrato unico.
# Ajustar o caminho conforme a posicao final de protocolo_composto/ na arvore.
from ..shared.strategy.base import CampoEsperado, ProtocoloStrategy
from ..shared.schemas.schema_resultado import PassoTrilha, SchemaResultado


class EstruturaInvalida(ValueError):
    """Erro ao traduzir o dado bruto (Models) para EstruturaComposta.
    Sempre erro de dado cadastrado (seed), nunca de resposta de paciente."""


class ProtocoloCompostoStrategy(ProtocoloStrategy):

    # ------------------------------------------------------------------
    # 1. carregar_estrutura: Models -> EstruturaComposta (Pydantic puro)
    # ------------------------------------------------------------------
    def carregar_estrutura(self, dado_bruto: Any) -> EstruturaComposta:
        """`dado_bruto` e o envelope que o Service monta a partir do
        repository (ver ExecucaoProtocoloService.buscar_dado_bruto_config):

            {
                "versao": ProtocoloVersao,
                "linhas": list[ProtocoloComposicao]  (com modulo_versao,
                    modulo e campos/variavel ja carregados via eager load),
                "config": ProtocoloComposicaoConfig | None,
            }

        Depois desta funcao, NADA mais toca o banco.
        """
        linhas = dado_bruto.get("linhas") or []
        config = dado_bruto.get("config")
        versao = dado_bruto.get("versao")

        if not linhas:
            raise EstruturaInvalida("composicao sem nenhum modulo associado")

        modulos: list[ModuloDef] = []
        variaveis: dict[str, VariavelDef] = {}

        for linha in linhas:
            mv = linha.modulo_versao
            modulo_model = mv.modulo

            campos: list[tuple[str, bool]] = []
            for campo in mv.campos:  # ModuloVersaoCampo, ja carregado
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

            modulos.append(ModuloDef(
                sigla=modulo_model.sigla,
                versao=mv.numero_versao,
                familia=modulo_model.familia_calculo,
                tipo_saida=modulo_model.tipo_saida,
                papel=linha.papel,
                grupo_agregacao=linha.grupo_agregacao,
                configuracao=mv.configuracao_json,
                campos=campos,
            ))

        gatilhos_papel = [m.sigla for m in modulos if m.papel == "gatilho"]
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

    # ------------------------------------------------------------------
    # 2. campos_esperados: a uniao de variaveis, achatada para o front
    # ------------------------------------------------------------------
    def campos_esperados(self, estrutura: EstruturaComposta) -> list[CampoEsperado]:
        campos = []
        for v in estrutura.variaveis.values():
            campos.append(CampoEsperado(
                campo=v.codigo,
                texto=v.nome,
                tipo_campo=v.tipo_dado,
                opcoes=[o["valor"] for o in v.opcoes] if v.opcoes else None,
            ))
        return campos

    # ------------------------------------------------------------------
    # 3. validar_respostas: contra o dicionario de variaveis (uniao)
    # ------------------------------------------------------------------
    def validar_respostas(self, estrutura: EstruturaComposta, respostas: dict) -> dict:
        desconhecidas = set(respostas) - set(estrutura.variaveis)
        if desconhecidas:
            raise ValueError(f"campo(s) desconhecido(s): {sorted(desconhecidas)}")

        validados: dict[str, Any] = {}
        for codigo, valor in respostas.items():
            var = estrutura.variaveis[codigo]

            if var.tipo_dado == "numerico":
                try:
                    valor_num = float(valor)
                except (TypeError, ValueError) as ex:
                    raise ValueError(f"'{codigo}': valor nao numerico ({valor!r})") from ex
                if var.valor_min is not None and valor_num < var.valor_min:
                    raise ValueError(f"'{codigo}': {valor_num} abaixo do minimo ({var.valor_min})")
                if var.valor_max is not None and valor_num > var.valor_max:
                    raise ValueError(f"'{codigo}': {valor_num} acima do maximo ({var.valor_max})")
                validados[codigo] = valor_num

            elif var.tipo_dado == "categorico":
                opcoes_validas = {o["valor"] for o in (var.opcoes or [])}
                if valor not in opcoes_validas:
                    raise ValueError(f"'{codigo}': valor {valor!r} fora das opcoes {sorted(opcoes_validas)}")
                validados[codigo] = valor

            elif var.tipo_dado == "booleano":
                if not isinstance(valor, bool):
                    raise ValueError(f"'{codigo}': esperado booleano, recebido {valor!r}")
                validados[codigo] = valor

            else:  # pragma: no cover - defensivo; tipo_dado e Literal fechado
                raise ValueError(f"'{codigo}': tipo_dado desconhecido {var.tipo_dado!r}")

        # variavel declarada e ausente: nao entra no dict (dado ausente,
        # tratado pelos avaliadores -- nao e erro aqui)
        return validados

    # ------------------------------------------------------------------
    # 4. executar: a orquestracao em si. Funcao pura.
    # ------------------------------------------------------------------
    def executar(self, estrutura: EstruturaComposta, dados_validados: dict) -> SchemaResultado:
        resultados: dict[str, ResultadoModulo] = {}

        # a) gatilhos primeiro (independentes entre si; ordem nao importa
        #    porque cada um so olha os proprios campos)
        for m in estrutura.modulos:
            if m.papel == "gatilho":
                resultados[m.sigla] = self._avaliar_um(m, dados_validados)

        # b) decide quem fica nao_aplicavel
        try:
            desligados = aplicar_gatilhos(estrutura.regra_gatilho, resultados)
        except GatilhoInvalido as ex:
            raise EstruturaInvalida(f"regra_gatilho_json invalida: {ex}") from ex

        # c) demais modulos
        for m in estrutura.modulos:
            if m.papel == "gatilho":
                continue
            if m.sigla in desligados:
                resultados[m.sigla] = ResultadoModulo(
                    sigla_modulo=m.sigla, versao=m.versao, status="nao_aplicavel",
                    tipo_saida=m.tipo_saida, motivo=desligados[m.sigla],
                )
            else:
                resultados[m.sigla] = self._avaliar_um(m, dados_validados)

        # d) agregacao por grupo (so participam papel != 'gatilho' e
        #    grupo_agregacao preenchido; o restante e sempre "paralelo")
        agregados_por_grupo: dict[str, Any] = {}
        modulos_por_grupo: dict[str, list[str]] = {}
        for m in estrutura.modulos:
            if m.papel != "gatilho" and m.grupo_agregacao:
                modulos_por_grupo.setdefault(m.grupo_agregacao, []).append(m.sigla)

        aviso_agregacao_parcial: list[str] = []
        classificacao_final = None
        valor_final = None

        if modulos_por_grupo and estrutura.agregacao != "nenhuma":
            # v1: um unico grupo agregado por protocolo (ver ressalva no
            # texto de resposta). Agrega o primeiro grupo encontrado.
            primeiro_grupo = next(iter(modulos_por_grupo))
            siglas_grupo = modulos_por_grupo[primeiro_grupo]
            resultados_grupo = [resultados[s] for s in siglas_grupo]
            try:
                agregado = agregar(estrutura.agregacao, resultados_grupo)
            except AgregacaoInvalida as ex:
                raise EstruturaInvalida(f"agregacao invalida: {ex}") from ex
            agregados_por_grupo[primeiro_grupo] = agregado.model_dump()
            classificacao_final = agregado.classificacao
            valor_final = agregado.valor
            if agregado.parcial:
                aviso_agregacao_parcial = agregado.modulos_excluidos
        else:
            agregado = agregar("nenhuma", list(resultados.values()))
            classificacao_final = agregado.classificacao

        # e) monta o contrato unico -- trilha concatenada e renumerada
        trilha_final: list[PassoTrilha] = []
        ordem = 0
        ausentes_uniao: list[str] = []
        for m in estrutura.modulos:
            r = resultados[m.sigla]
            ausentes_uniao.extend(r.ausentes)
            for passo in r.trilha:
                trilha_final.append(PassoTrilha(
                    rotulo=passo.rotulo,
                    valor_observado=passo.valor_observado,
                    peso_ou_resultado=passo.contribuicao,
                    ordem=ordem,
                ))
                ordem += 1

        alertas = [
            {"modulo": r.sigla_modulo, "classificacao": r.classificacao, "motivo": r.motivo}
            for m, r in zip(estrutura.modulos, [resultados[m.sigla] for m in estrutura.modulos])
            if m.papel != "gatilho"
            and r.tipo_saida == "flag" and r.status == "calculado" and r.valor is True
        ]

        return SchemaResultado(
            classificacao=classificacao_final,
            trilha_explicativa=trilha_final,
            dados_ausentes=sorted(set(ausentes_uniao)),
            metadata={
                "modulos": [r.model_dump() for r in resultados.values()],
                "alertas": alertas,
                "agregacao": {
                    "tipo": estrutura.agregacao,
                    "valor": valor_final,
                    "grupos": agregados_por_grupo,
                    "parcial": bool(aviso_agregacao_parcial),
                    "modulos_excluidos": aviso_agregacao_parcial,
                },
                "codigo_composicao": estrutura.codigo_composicao,
            },
        )

    # ------------------------------------------------------------------
    def _avaliar_um(self, modulo: ModuloDef, dados: dict) -> ResultadoModulo:
        avaliador = AVALIADORES.get(modulo.familia)
        if avaliador is None:  # pragma: no cover - defensivo; familia e Literal fechado
            raise EstruturaInvalida(f"familia sem avaliador registrado: {modulo.familia!r}")
        return avaliador(modulo, dados)
