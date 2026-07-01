"""Helpers de resposta JSON padronizada para toda a API."""

from flask import jsonify


def json_success(data=None, message="ok", status=200):
    return jsonify({"status": "success", "message": message, "data": data}), status


def json_error(message="erro", status=400):
    return jsonify({"status": "error", "message": message}), status
