"""Testes unitarios de src/core/security.py (Argon2, AES-256-GCM, HMAC)."""

import os
import pytest

os.environ.setdefault("AES_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
os.environ.setdefault("HMAC_KEY", "chave-teste-hmac")

from src.core.security import ph, aes_encrypt, aes_decrypt, hmac_sha256


def test_argon2_hash_e_verify():
    h = ph.hash("minha-senha-forte")
    assert h != "minha-senha-forte"
    ph.verify(h, "minha-senha-forte")  # não deve lançar exceção


def test_aes_encrypt_decrypt_roundtrip():
    original = "João da Silva - CPF 222.222.222-22"
    cifrado = aes_encrypt(original)
    assert cifrado != original
    assert aes_decrypt(cifrado) == original


def test_aes_encrypt_none_retorna_none():
    assert aes_encrypt(None) is None
    assert aes_decrypt(None) is None


def test_aes_cada_chamada_gera_ciphertext_diferente():
    """Nonce aleatório por chamada: mesmo texto claro nunca gera o mesmo
    ciphertext duas vezes (propriedade de segurança do GCM)."""
    c1 = aes_encrypt("mesmo texto")
    c2 = aes_encrypt("mesmo texto")
    assert c1 != c2
    assert aes_decrypt(c1) == aes_decrypt(c2) == "mesmo texto"


def test_hmac_sha256_e_deterministico():
    """Ao contrário do AES, o HMAC precisa ser determinístico (mesmo CPF
    sempre gera o mesmo hash, usado como índice de busca pós-anonimização)."""
    h1 = hmac_sha256("222.222.222-22")
    h2 = hmac_sha256("222.222.222-22")
    assert h1 == h2
    assert len(h1) == 64  # hex de sha256
