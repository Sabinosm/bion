from pathlib import Path

from src.domains.exames.loinc.carregar_loinc_service import executar as executar_loinc
from src.domains.exames.importacao.importar_catalogo_exames_service import executar as executar_catalogo_exames
from src.domains.exames.conteudo.sincronizar_conteudo_exames_service import executar as executar_conteudo_exames

PASTA = Path(__file__).parent  # seeds/exames


def executar(incluir_pt: bool = False, limite: int = 10,
             dry_run_catalogos_exame: bool = False, carregar_loinc: bool = True):
    if carregar_loinc:
        print(executar_loinc(
            str(PASTA / "loinc.csv"),
            versao="1.0",
            caminho_pt=str(PASTA / "pt_br_variant.csv"),
            caminho_paineis=str(PASTA / "panels_and_forms.csv"),
        ))

    print(executar_catalogo_exames(
        str(PASTA / "exames_brasil_candidatos.csv"),
        dry_run=dry_run_catalogos_exame,
    ))
    
    idiomas = ("en", "pt") if incluir_pt else ("en",)
    print(executar_conteudo_exames(idiomas=idiomas, limite=limite))