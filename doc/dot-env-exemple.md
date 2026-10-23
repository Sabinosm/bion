# Flask
FLASK_ENV=
SECRET_KEY=

# Banco de dados
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=
DB_NAME=

# Criptografia (ver src/core/security.py)
# AES_KEY precisa ser uma chave de 32 bytes (AES-256) codificada em base64.
# Gerar uma nova com: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
AES_KEY=
HMAC_KEY=
TOTP_ENCRYPTION_KEY=
# Motor de IA (protocolos de suporte a decisao)
BION_IA_PROVEDOR=
BION_IA_MODELO=
GEMINI_API_KEY=

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=

RP_ID=
RP_NAME=

CONSENT_BLOQUEIA_CONSULTA=
CONSENT_JANELA_COPIA_MIN=
OPERADOR_NOME=

SUPABASE_URL=
SUPABASE_KEY=
SUPABASE_BUCKET=
DETECTA_INTERACOES_API_KEY=
