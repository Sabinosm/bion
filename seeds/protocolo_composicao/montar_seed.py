"""Ponto de entrada do seed. Roda TODAS as validacoes antes de gerar
qualquer coisa que seria persistida -- espelha o checklist de validacoes
combinado no desenho (variaveis usadas == declaradas, faixas sem buraco,
agregacao compativel com tipo_saida, codigo_composicao sempre derivado,
gatilho nao referencia modulo fora da composicao nem desliga outro
gatilho, composicao so em escopo_uso='consulta').

Este arquivo NAO toca banco -- devolve estruturas Python prontas para o
codigo real (seed real do projeto) persistir via SQLAlchemy. Rodar como
`python -m seed.montar_seed` para ver o relatorio de validacao.
"""
from .variaveis import VARIAVEIS
from .modulos import MODULOS, MODULOS_POR_SIGLA
from .composicoes import COMPOSICOES

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.domains.protocolo.protocolo_composto.schemas.config_schemas import validar_configuracao  # noqa: E402
from src.domains.protocolo.protocolo_composto.logic.condicao_protocolo_composto import validar_estrutura  # noqa: E402


class SeedInvalido(Exception):
    """Qualquer violacao encontrada aqui deve travar o deploy do seed."""


TIPOS_RESULTADO_VALIDOS = {"score-numerico", "categoria-cor", "nivel-risco", "binario"}


def _variaveis_por_codigo():
    codigos = [v["codigo"] for v in VARIAVEIS]
    dups = {c for c in codigos if codigos.count(c) > 1}
    if dups:
        raise SeedInvalido(f"variavel_clinica duplicada: {dups}")
    return {v["codigo"]: v for v in VARIAVEIS}


def validar_modulos(variaveis_por_codigo: dict) -> None:
    for m in MODULOS:
        # 1. configuracao_json valida contra o schema da familia declarada
        try:
            config = validar_configuracao(m["familia_calculo"], m["configuracao_json"])
        except Exception as ex:
            raise SeedInvalido(f"[{m['sigla']}] configuracao_json invalida: {ex}") from ex

        # 2. variaveis usadas na config == variaveis declaradas em campos
        usadas = config.variaveis_usadas()
        declaradas = {codigo for codigo, _obrig in m["campos"]}
        if usadas != declaradas:
            faltando_em_campos = usadas - declaradas
            sobrando_em_campos = declaradas - usadas
            partes = []
            if faltando_em_campos:
                partes.append(f"usadas na config mas nao declaradas em campos: {sorted(faltando_em_campos)}")
            if sobrando_em_campos:
                partes.append(f"declaradas em campos mas nao usadas na config: {sorted(sobrando_em_campos)}")
            raise SeedInvalido(f"[{m['sigla']}] inconsistencia de variaveis — {'; '.join(partes)}")

        # 3. toda variavel usada existe no dicionario compartilhado
        desconhecidas = usadas - set(variaveis_por_codigo)
        if desconhecidas:
            raise SeedInvalido(f"[{m['sigla']}] variavel(is) nao cadastrada(s) em variavel_clinica: {sorted(desconhecidas)}")

        # 4. explicacao_json tem os campos obrigatorios
        exigidos = {"o_que_e", "quando_usar", "como_interpretar"}
        faltando = exigidos - set(m["explicacao_json"])
        if faltando:
            raise SeedInvalido(f"[{m['sigla']}] explicacao_json sem campos obrigatorios: {faltando}")

        # 5. indice_bit dentro do limite seguro (ver nota sobre POW/DOUBLE no SQL)
        if not (0 <= m["indice_bit"] <= 62):
            raise SeedInvalido(f"[{m['sigla']}] indice_bit fora do intervalo seguro (0-62): {m['indice_bit']}")


def _calcular_bitmask(siglas_modulos: list[str]) -> int:
    bitmask = 0
    for sigla in siglas_modulos:
        modulo = MODULOS_POR_SIGLA[sigla]
        bitmask |= 1 << modulo["indice_bit"]
    return bitmask


def validar_composicoes() -> dict[str, int]:
    """Retorna {sigla_protocolo: codigo_composicao calculado}."""
    codigos_por_protocolo: dict[str, int] = {}
    codigos_ja_usados: dict[int, str] = {}

    for comp in COMPOSICOES:
        siglas = [sigla for sigla, _papel, _grupo in comp["modulos"]]

        # 1. escopo_uso precisa ser 'consulta' (decisao fechada no projeto)
        if comp["escopo_uso"] != "consulta":
            raise SeedInvalido(f"[{comp['sigla_protocolo']}] composicao precisa ter escopo_uso='consulta'")

        # 1b. tipo_resultado precisa ser um dos 4 valores do Enum do banco
        # (NOT NULL em protocolo_catalogo; pega erro de digitacao aqui,
        # nao como IntegrityError na hora de gravar)
        if comp.get("tipo_resultado") not in TIPOS_RESULTADO_VALIDOS:
            raise SeedInvalido(
                f"[{comp['sigla_protocolo']}] tipo_resultado invalido ou ausente: "
                f"{comp.get('tipo_resultado')!r} (precisa ser um de {sorted(TIPOS_RESULTADO_VALIDOS)})"
            )

        # 2. modulo referenciado precisa existir no catalogo
        desconhecidos = set(siglas) - set(MODULOS_POR_SIGLA)
        if desconhecidos:
            raise SeedInvalido(f"[{comp['sigla_protocolo']}] modulo(s) inexistente(s): {desconhecidos}")

        # 3. sigla de modulo nao pode se repetir na mesma composicao
        if len(siglas) != len(set(siglas)):
            raise SeedInvalido(f"[{comp['sigla_protocolo']}] modulo repetido na composicao: {siglas}")

        # 4. gatilhos: precisam existir na composicao e nao desligar outro gatilho
        papel_por_sigla = {sigla: papel for sigla, papel, _grupo in comp["modulos"]}
        if comp["regra_gatilho_json"]:
            for g in comp["regra_gatilho_json"]["gatilhos"]:
                if g["modulo"] not in papel_por_sigla:
                    raise SeedInvalido(f"[{comp['sigla_protocolo']}] gatilho referencia modulo fora da composicao: {g['modulo']}")
                if papel_por_sigla[g["modulo"]] != "gatilho":
                    raise SeedInvalido(f"[{comp['sigla_protocolo']}] '{g['modulo']}' usado como gatilho mas papel declarado é '{papel_por_sigla[g['modulo']]}'")
                for alvo in g["desliga"]:
                    if alvo not in papel_por_sigla:
                        raise SeedInvalido(f"[{comp['sigla_protocolo']}] gatilho desliga modulo fora da composicao: {alvo}")
                    if papel_por_sigla[alvo] == "gatilho":
                        raise SeedInvalido(f"[{comp['sigla_protocolo']}] gatilho não pode desligar outro gatilho: {alvo}")

        # 5. agregacao compativel com tipo_saida dos modulos do grupo
        if comp["agregacao"] != "nenhuma":
            tipos_saida = {MODULOS_POR_SIGLA[s]["tipo_saida"] for s, papel, grupo in comp["modulos"]
                           if papel != "gatilho" and grupo is not None}
            exigido = {"soma": "pontos", "maximo": "pontos", "pior_categoria": "categoria", "any_flag": "flag"}[comp["agregacao"]]
            incompativeis = tipos_saida - {exigido}
            if incompativeis:
                raise SeedInvalido(f"[{comp['sigla_protocolo']}] agregacao '{comp['agregacao']}' incompativel com tipo_saida presente: {incompativeis}")

        # 6. codigo_composicao: calculado e checado contra colisao
        codigo = _calcular_bitmask(siglas)
        if codigo in codigos_ja_usados:
            raise SeedInvalido(
                f"[{comp['sigla_protocolo']}] codigo_composicao {codigo} colide com "
                f"'{codigos_ja_usados[codigo]}' (mesmo conjunto de modulos)"
            )
        codigos_ja_usados[codigo] = comp["sigla_protocolo"]
        codigos_por_protocolo[comp["sigla_protocolo"]] = codigo

    return codigos_por_protocolo


def rodar_validacao_completa() -> dict:
    """Roda tudo. Levanta SeedInvalido na primeira violacao encontrada.
    Retorna um resumo para relatorio (usado pelo __main__ abaixo)."""
    variaveis_por_codigo = _variaveis_por_codigo()
    validar_modulos(variaveis_por_codigo)
    codigos = validar_composicoes()
    return {
        "total_variaveis": len(variaveis_por_codigo),
        "total_modulos": len(MODULOS),
        "total_composicoes": len(COMPOSICOES),
        "codigos_composicao": codigos,
    }


if __name__ == "__main__":
    resultado = rodar_validacao_completa()
    print(f"Variáveis: {resultado['total_variaveis']}")
    print(f"Módulos: {resultado['total_modulos']}")
    print(f"Composições: {resultado['total_composicoes']}")
    print("Códigos de composição (bitmask):")
    for sigla, codigo in resultado["codigos_composicao"].items():
        print(f"  {sigla}: {codigo} (0b{codigo:010b}, hex 0x{codigo:03X})")
    print("\nSeed válido.")