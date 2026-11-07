"""Ponto de entrada da aplicacao (WSGI). Uso: flask run / gunicorn app:app"""

import os
from src.main import create_app
from seeds.seedNews2 import seed_news2
from seeds.protocolo_composicao.persistir import seed_composicao
from seeds.exames.executar import executar as seed_exames
from seeds.seed_loinc_vital import seed as seed_loinc_vital
from seeds.pacientes.seed_pacientes import seed_pacientes
from seeds.profissionais.seed_profissionais import seed_profissionais

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
       #with app.app_context(): 
              #seed_news2()
              #seed_composicao()
              #seed_exames(incluir_pt=True, limite=100)
              #seed_loinc_vital()
              #seed_pacientes()
              #seed_profissionais()
                            
       app.run(host="0.0.0.0", port=5000, debug=True)
       

