"""Ponto de entrada da aplicacao (WSGI). Uso: flask run / gunicorn app:app"""

import os
from src.main import create_app
from seeds.seedNews2 import seed_news2

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
        
       app.run(host="0.0.0.0", port=5000, debug=True)
       

