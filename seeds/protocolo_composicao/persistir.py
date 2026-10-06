"""Persiste o seed (variaveis, modulos, composicoes) via SQLAlchemy.

IDEMPOTENTE: rodar duas vezes nao duplica nada. A identidade de cada
entidade para fins de upsert e sempre um campo de NEGOCIO estavel, nunca
a posicao na lista Python:
    - VariavelClinica   por `codigo`
    - CatalogoModulos   por `sigla`
    - ModuloVersao      por (id_modulo, numero_versao)
    - ProtocoloCatalogo por `sigla`
    - ProtocoloVersao   por (id_protocolo_catalogo, numero_versao)
    - ProtocoloComposicao       recriada inteira a cada rodada (ver nota)
    - ProtocoloComposicaoConfig upsert por id_protocolo_versao

SEMPRE valida com rodar_validacao_completa() ANTES de tocar o banco --
se o seed estiver inconsistente, nada e escrito (aborta antes do primeiro
INSERT, nao no meio).

Uso:
    python -m seed.persistir_seed            # aplica
    python -m seed.persistir_seed --dry-run  # so valida e mostra o plano
"""
import argparse
import sys

from src.models import db
from src.models.protocolos import (
    CatalogoModulos,
    ModuloVersao,
    ModuloVersaoCampo,
    ProtocoloCatalogo,
    ProtocoloComposicao,
    ProtocoloComposicaoConfig,
    ProtocoloVersao,
    VariavelClinica,
)

from .composicoes import COMPOSICOES
from .modulos import MODULOS
from .montar_seed import SeedInvalido, rodar_validacao_completa
from .variaveis import VARIAVEIS


def _upsert_variaveis() -> dict[str, VariavelClinica]:
    """Retorna {codigo: instancia}, criando o que faltar e atualizando o
    que ja existe (por codigo). Nunca duplica."""
    por_codigo: dict[str, VariavelClinica] = {
        v.codigo: v for v in VariavelClinica.query.all()
    }
    for dado in VARIAVEIS:
        existente = por_codigo.get(dado["codigo"])
        if existente is None:
            existente = VariavelClinica(codigo=dado["codigo"])
            db.session.add(existente)
            por_codigo[dado["codigo"]] = existente

        existente.nome = dado["nome"]
        existente.tipo_dado = dado["tipo_dado"]
        existente.unidade = dado.get("unidade")
        existente.opcoes_json = dado.get("opcoes")
        existente.valor_min = dado.get("valor_min")
        existente.valor_max = dado.get("valor_max")

    db.session.flush()  # garante id_variavel disponivel para os proximos passos
    return por_codigo


def _upsert_modulos_e_versoes(
    variaveis_por_codigo: dict[str, VariavelClinica],
) -> dict[str, ModuloVersao]:
    """Retorna {sigla_modulo: ModuloVersao da versao '1.0'} -- hoje o seed
    so declara a versao 1.0 de cada modulo; uma correcao futura de um
    modulo publicado deve criar numero_versao='1.1' etc. em vez de editar
    esta funcao para sobrescrever '1.0' (versao publicada e imutavel)."""
    modulos_por_sigla: dict[str, CatalogoModulos] = {
        m.sigla: m for m in CatalogoModulos.query.all()
    }
    versao_por_sigla: dict[str, ModuloVersao] = {}

    for dado in MODULOS:
        modulo = modulos_por_sigla.get(dado["sigla"])
        if modulo is None:
            modulo = CatalogoModulos(sigla=dado["sigla"])
            db.session.add(modulo)
            modulos_por_sigla[dado["sigla"]] = modulo

        # indice_bit e imutavel uma vez atribuido -- se ja existe, so
        # confere que o seed nao esta tentando reatribuir (o que
        # invalidaria codigo_composicao ja gravados); se e novo, atribui.
        if modulo.indice_bit is not None and modulo.indice_bit != dado["indice_bit"]:
            raise SeedInvalido(
                f"[{dado['sigla']}] indice_bit mudaria de {modulo.indice_bit} para "
                f"{dado['indice_bit']} -- isso invalidaria codigo_composicao ja "
                f"gravados. Nunca reordene MODULOS em seed/modulos.py."
            )

        modulo.nome_modulo = dado["nome_modulo"]
        modulo.tipo_modulo = dado["tipo_modulo"]
        modulo.familia_calculo = dado["familia_calculo"]
        modulo.tipo_saida = dado["tipo_saida"]
        modulo.indice_bit = dado["indice_bit"]
        db.session.flush()  # garante id_modulo

        versao = ModuloVersao.query.filter_by(
            id_modulo=modulo.id, numero_versao=dado["versao"]
        ).first()
        if versao is None:
            versao = ModuloVersao(id_modulo=modulo.id, numero_versao=dado["versao"])
            db.session.add(versao)
        elif versao.status == "ativa":
            # versao ja publicada: nao sobrescreve config/explicacao em
            # runtime (regra de imutabilidade). Se o conteudo do seed
            # mudou para esta mesma numero_versao, isso e erro do seed
            # (deveria ter incrementado a versao), nao algo a aplicar.
            if versao.configuracao_json != dado["configuracao_json"]:
                raise SeedInvalido(
                    f"[{dado['sigla']}] v{dado['versao']} já está publicada e ativa, "
                    f"mas o configuracao_json do seed mudou -- crie uma nova "
                    f"numero_versao em vez de editar uma versão publicada."
                )
            versao_por_sigla[dado["sigla"]] = versao
            continue

        versao.configuracao_json = dado["configuracao_json"]
        versao.explicacao_json = dado["explicacao_json"]
        versao.status = "ativa"
        db.session.flush()  # garante id_modulo_versao

        _sincronizar_campos(versao, dado["campos"], variaveis_por_codigo)
        versao_por_sigla[dado["sigla"]] = versao

    return versao_por_sigla


def _sincronizar_campos(
    versao: ModuloVersao,
    campos: list[tuple[str, bool]],
    variaveis_por_codigo: dict[str, VariavelClinica],
) -> None:
    existentes = {c.id: c for c in ModuloVersaoCampo.query.filter_by(
        id_modulo_versao=versao.id
    ).all()}
    desejados_ids = set()

    for ordem, (codigo_variavel, obrigatorio) in enumerate(campos):
        variavel = variaveis_por_codigo[codigo_variavel]  # ja validado antes de chegar aqui
        desejados_ids.add(variavel.id)
        existente = existentes.get(variavel.id)
        if existente is None:
            db.session.add(ModuloVersaoCampo(
                id_modulo_versao=versao,
                id_variavel=variavel.id,
                obrigatorio=obrigatorio,
                ordem=ordem,
            ))
        else:
            existente.obrigatorio = obrigatorio
            existente.ordem = ordem

    # remove campos que sobraram (nao estao mais na lista do seed)
    for id_variavel, campo in existentes.items():
        if id_variavel not in desejados_ids:
            db.session.delete(campo)


def _upsert_composicoes(versao_por_sigla_modulo: dict[str, ModuloVersao]) -> dict[str, int]:
    """Retorna {sigla_protocolo: codigo_composicao efetivamente gravado}."""
    codigos: dict[str, int] = {}

    for comp in COMPOSICOES:
        catalogo = ProtocoloCatalogo.query.filter_by(sigla=comp["sigla_protocolo"]).first()
        if catalogo is None:
            catalogo = ProtocoloCatalogo(sigla=comp["sigla_protocolo"])
            db.session.add(catalogo)

        catalogo.nome_protocolo = comp["nome_protocolo"]
        catalogo.tipo_protocolo = "protocolo-composto"
        catalogo.escopo_uso = comp["escopo_uso"]
        catalogo.status = "ativo"
        db.session.flush()  # garante id_protocolo_catalogo

        versao = ProtocoloVersao.query.filter_by(
            id_protocolo_catalogo=catalogo.id, numero_versao="1.0"
        ).first()
        if versao is None:
            versao = ProtocoloVersao(id_protocolo_catalogo=catalogo.id, numero_versao="1.0")
            db.session.add(versao)

        codigo = 0
        for sigla_modulo, _papel, _grupo in comp["modulos"]:
            codigo |= 1 << versao_por_sigla_modulo[sigla_modulo].modulo.indice_bit

        versao.codigo_composicao = codigo
        versao.status = "ativa"
        db.session.flush()  # garante id_versao
        codigos[comp["sigla_protocolo"]] = codigo

        _sincronizar_composicao_linhas(versao, comp, versao_por_sigla_modulo)
        _upsert_config(versao, comp)

    return codigos


def _sincronizar_composicao_linhas(versao, comp, versao_por_sigla_modulo) -> None:
    """A composicao inteira e recriada a cada rodada (delete + insert),
    porque nao ha um campo de negocio estavel por LINHA (uma linha e so
    'este par protocolo-versao/modulo-versao existe ou nao') -- ao
    contrario de modulo/variavel/protocolo, que tem sigla/codigo proprios.
    Isso e seguro porque protocolo_composicao nao carrega historico
    proprio: quem referencia uma versao especifica de modulo, para fins
    de auditoria, e InputProtocoloExecucao.id_versao_utilizada ->
    protocolo_versao, que nunca e tocado aqui."""
    ProtocoloComposicao.query.filter_by(id_protocolo_versao=versao.id).delete()
    for ordem, (sigla_modulo, papel, grupo) in enumerate(comp["modulos"]):
        db.session.add(ProtocoloComposicao(
            id_protocolo_versao=versao.id,
            id_modulo_versao=versao_por_sigla_modulo[sigla_modulo].id,
            papel=papel,
            grupo_agregacao=grupo,
            ordem=ordem,
        ))


def _upsert_config(versao, comp) -> None:
    config = ProtocoloComposicaoConfig.query.filter_by(id_protocolo_versao=versao.id).first()
    if config is None:
        config = ProtocoloComposicaoConfig(id_protocolo_versao=versao.id)
        db.session.add(config)
    config.agregacao = comp["agregacao"]
    config.regra_gatilho_json = comp["regra_gatilho_json"]


def persistir(dry_run: bool = False) -> dict:
    """Ponto de entrada. Valida tudo ANTES de qualquer escrita; se
    dry_run=True, faz rollback no final mesmo que tudo tenha corrido bem
    (util para ver o plano sem aplicar)."""
    resultado_validacao = rodar_validacao_completa()  # levanta SeedInvalido se algo estiver errado

    try:
        variaveis_por_codigo = _upsert_variaveis()
        versao_por_sigla_modulo = _upsert_modulos_e_versoes(variaveis_por_codigo)
        codigos_gravados = _upsert_composicoes(versao_por_sigla_modulo)

        # o codigo calculado pelo validador (em memoria) e o gravado
        # devem bater -- se nao baterem, algo divergiu entre a validacao
        # e a persistencia (bug neste script, nao no seed)
        if codigos_gravados != resultado_validacao["codigos_composicao"]:
            raise SeedInvalido(
                f"codigo_composicao gravado diverge do validado: "
                f"gravado={codigos_gravados} validado={resultado_validacao['codigos_composicao']}"
            )

        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {**resultado_validacao, "codigos_composicao": codigos_gravados, "aplicado": not dry_run}


if __name__ == "__main__":
    from src.main import create_app
    with create_app().app_context():

        parser = argparse.ArgumentParser()
        parser.add_argument("--dry-run", action="store_true", help="Só valida e mostra o plano, sem gravar.")
        args = parser.parse_args()

        try:
            resultado = persistir(dry_run=args.dry_run)
        except SeedInvalido as ex:
            print(f"SEED INVÁLIDO — nada foi gravado.\n{ex}", file=sys.stderr)
            sys.exit(1)

        modo = "DRY-RUN (nada foi gravado)" if not resultado["aplicado"] else "APLICADO"
        print(f"[{modo}]")
        print(f"Variáveis: {resultado['total_variaveis']}")
        print(f"Módulos: {resultado['total_modulos']}")
        print(f"Composições: {resultado['total_composicoes']}")
        for sigla, codigo in resultado["codigos_composicao"].items():
            print(f"  {sigla}: codigo_composicao={codigo}")