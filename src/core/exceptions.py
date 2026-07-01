"""Excecoes de dominio do Bion, mapeadas para status HTTP no error handler global."""


class BionException(Exception):
    status_code = 500

    def __init__(self, message="Erro interno.", status_code=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class RecursoNaoEncontradoError(BionException):
    status_code = 404


class PermissaoNegadaError(BionException):
    status_code = 403


class AutenticacaoError(BionException):
    status_code = 401


class DadosInvalidosError(BionException):
    status_code = 422


class ConflictoError(BionException):
    status_code = 409
