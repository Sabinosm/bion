"""Ponto de entrada da aplicacao (WSGI). Uso: flask run / gunicorn app:app"""

import os
from src.main import create_app
from seeds.seedNews2 import seed_news2
from seeds.protocolo_composicao.persistir import seed_composicao
from seeds.exames.executar import executar as seed_exames
from seeds.seed_loinc_vital import seed as seed_loinc_vital
from seeds.pacientes.seed_pacientes import seed_pacientes
from seeds.profissionais.seed_profissionais import seed_profissionais
from seeds.atendimentos.seed_atendimentos import main as seed_atendimentos
from seeds.consultas.seed_consultas import main as seed_consultas

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
       with app.app_context(): 
              #seed_news2()
              #seed_composicao()
              #seed_exames(incluir_pt=True, limite=100)
              #seed_loinc_vital()
              #seed_pacientes(empresa=60018, dry_run=False, app=app)
              #seed_consultas(empresa=60018, dry_run=False, id_usuario=30012)
              #seed_profissionais(empresa=60018, dry_run=False, app=app)
              seed_atendimentos(empresa=60018, ate=100, validar=False, seed=2026)
                            
       app.run(host="0.0.0.0", port=5000, debug=True)
       

