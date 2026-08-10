"""Configuração central do WebAuthn (RP ID e origin esperado).

Centraliza aqui porque `expected_origin` PRECISA ser uma URL completa
com esquema (ex.: "https://app.bion.com.br"), não um host puro como
"127.0.0.1" -- é assim que o navegador preenche `clientDataJSON.origin`,
e é contra esse valor exato que a lib compara. Usar só o host funciona
por acidente em alguns ambientes de dev e quebra sempre em produção
com HTTPS real.

Definido via variáveis de ambiente para não hardcodar por arquivo:

    WEBAUTHN_RP_ID=127.0.0.1              (dev, sem porta/esquema)
    WEBAUTHN_ORIGIN=http://127.0.0.1:5000 (dev, URL completa)

    WEBAUTHN_RP_ID=app.bion.com.br
    WEBAUTHN_ORIGIN=https://app.bion.com.br

Se as variáveis não estiverem definidas, cai em um default de
desenvolvimento local -- nunca em produção, porque lá elas devem ser
sempre setadas explicitamente no ambiente do deploy.
"""

import os

RP_ID = os.environ.get("WEBAUTHN_RP_ID", "localhost")
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Bion")
EXPECTED_ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "http://localhost:5000")