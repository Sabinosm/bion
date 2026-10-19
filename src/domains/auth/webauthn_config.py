"""Configuração central do WebAuthn (RP ID e origin esperado).
"""

import os

# O domínio de onde a chave "pertence" (SEM https:// e SEM porta)
RP_ID = os.environ.get("WEBAUTHN_RP_ID", "bion-one.vercel.app")

# Nome exibido na tela de biometria do usuário
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Bion")

# A origem exata de onde vem o clique do usuário (COM https://)
EXPECTED_ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "https://bion-one.vercel.app")
