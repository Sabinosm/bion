"""Configuração central do WebAuthn (RP ID e origin esperado).

`EXPECTED_ORIGIN` precisa ser uma URL completa com esquema (ex.:
"https://app.bion.com.br"), nunca um host puro como "127.0.0.1" —
é assim que o navegador preenche `clientDataJSON.origin`, e é contra
esse valor exato que a lib compara.

Definido via variáveis de ambiente para não hardcodar por arquivo:

    WEBAUTHN_RP_ID=127.0.0.1              (dev, sem porta/esquema)
    WEBAUTHN_ORIGIN=http://127.0.0.1:5000 (dev, URL completa)

    WEBAUTHN_RP_ID=app.bion.com.br
    WEBAUTHN_ORIGIN=https://app.bion.com.br

Sem as variáveis, cai em um default de desenvolvimento local — em
produção elas devem ser sempre setadas explicitamente no ambiente do
deploy.
"""

import os

# O domínio de onde a chave "pertence" (SEM https:// e SEM porta)
RP_ID = os.environ.get("WEBAUTHN_RP_ID", "bion-one.vercel.app")

# Nome exibido na tela de biometria do usuário
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Bion")

# A origem exata de onde vem o clique do usuário (COM https://)
EXPECTED_ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "https://bion-one.vercel.app")
