"""Helpers de resposta JSON padronizada para toda a API."""

from flask import jsonify


def json_success(data=None, message="ok", status=200):
    return jsonify({"status": "success", "message": message, "data": data}), status


def json_error(message="erro", status=400, erros=None):
    """`erros` (opcional) = {campo: mensagem}, para o front pintar o erro
    no input certo sem depender do texto de `message`. Chave especial
    "_geral" = erro sem campo definido."""
    corpo = {"status": "error", "message": message}
    if erros:
        corpo["erros"] = erros
    return jsonify(corpo), status