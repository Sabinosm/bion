"""
Segurança e criptografia do Bion.

- Argon2id para hash de senhas (instância global `ph`).
- AES-256-GCM para campos sensíveis em repouso (PII em Paciente_pessoal,
  CPF em Usuario, etc).
- HMAC-SHA256 para pseudoanonimização (identificador estável de paciente
  após exclusão de dados pessoais por solicitação LGPD).
"""

import os
import base64
import hmac
import hashlib

from argon2 import PasswordHasher
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ph = PasswordHasher()


def _aes_key() -> bytes:
    return base64.b64decode(os.getenv("AES_KEY", ""))


def aes_encrypt(plaintext: str) -> str:
    """AES-256-GCM. Retorna base64(nonce + ciphertext)."""
    if plaintext is None:
        return None
    key = _aes_key()
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def aes_decrypt(token: str) -> str:
    if token is None:
        return None
    key = _aes_key()
    data = base64.b64decode(token)
    return AESGCM(key).decrypt(data[:12], data[12:], None).decode()


def hmac_sha256(value: str) -> str:
    """Pseudoanonimização: ex. CPF após exclusão de dados pessoais (LGPD)."""
    secret = os.getenv("HMAC_KEY", "").encode()
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()
