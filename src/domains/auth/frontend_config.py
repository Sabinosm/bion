"""Configuração da URL base do frontend.

O frontend (html/pages/...) roda num servidor separado do Flask
(ex.: Vite, live-server) -- em dev, tipicamente uma porta diferente
na mesma máquina (http://localhost:5500), e em produção um domínio
publicado à parte do backend.

Por isso redirects do backend para páginas do frontend (como depois
do callback do Google OAuth) não podem usar paths relativos como
redirect("/paginas/pos-login.html") -- isso é resolvido pelo
navegador contra a origem atual, que nesse ponto é o Flask
(localhost:5000), não o frontend. É preciso montar a URL completa.

    FRONTEND_URL=http://localhost:5500        (dev)
    FRONTEND_URL=https://app.bion.com.br      (produção)
"""

import os

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5500").rstrip("/")