"""Ponto de entrada da aplicacao (WSGI). Uso: flask run / gunicorn app:app"""

import os
from src.main import create_app
from seeds.seedNews2 import seed_news2
from seeds.protocolo_composicao.persistir import seed_composicao
from seeds.exames.executar import executar
from seeds.seed_loinc_vital import seed
from seeds.pacientes.seed_pacientes import seed_pacientes

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
       with app.app_context(): 
              #seed_news2()
              #seed_composicao()
              #executar(incluir_pt=True, limite=100)
              #print(seed())
              resultado = seed_pacientes(empresa=60018, dry_run=True, app=app)
              if not resultado["ok"]:
                     for e in resultado["erros"]:
                            print(e["linha"], e["paciente"], e["erro"])
                            
       app.run(host="0.0.0.0", port=5000, debug=True)
       

