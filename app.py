"""Ponto de entrada da aplicacao (WSGI). Uso: flask run / gunicorn app:app"""

import os
from src.main import create_app

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", True))
