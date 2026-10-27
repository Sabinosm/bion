"""Ponto de entrada da aplicacao (WSGI). Uso: flask run / gunicorn app:app"""

import os
from src.main import create_app
from seeds.seedNews2 import seed_news2
from seeds.protocolo_composicao.persistir import seed_composicao
from src.domains.exames.importacao.importar_catalogo_exames_service import executar as executar_catalogo_exames
from src.domains.exames.conteudo.sincronizar_conteudo_exames_service import executar as executar_conteudo_exames
from src.domains.exames.loinc.carregar_loinc_service import executar as executar_loinc

CAMINHO_BASE_LOINC = "seeds/exames/"

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
       #with app.app_context(): 
              #seed_news2()
              #seed_composicao()
              #executar()
              #print(executar_conteudo_exames())
              #print(executar_loinc(
                     # versao="1.0",caminho_paineis=CAMINHO_BASE_LOINC+"panels_and_forms.csv", 
                     # caminho_loinc=CAMINHO_BASE_LOINC+"loinc.csv", 
                     # caminho_pt=CAMINHO_BASE_LOINC+"pt_br_variant.csv"))
                     
       app.run(host="0.0.0.0", port=5000, debug=True)
       

