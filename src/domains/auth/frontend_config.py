"""Configuração da URL base do frontend.

O frontend roda num servidor separado do Flask (ex.: Vite,
live-server), com origem própria — em dev, geralmente outra porta na
mesma máquina; em produção, outro domínio. Por isso redirects do
backend para páginas do frontend (ex.: pós-login do Google OAuth)
precisam montar a URL completa a partir de FRONTEND_URL, nunca um path
relativo: um path relativo seria resolvido pelo navegador contra a
origem do Flask, não a do frontend.

    FRONTEND_URL=http://localhost:5500        (dev)
    FRONTEND_URL=https://app.bion.com.br      (produção)
"""

import os

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://bion-one.vercel.app").rstrip("/")
