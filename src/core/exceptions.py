"""Excecoes de dominio do Bion, mapeadas para status HTTP no error handler global."""


class BionException(Exception):
    status_code = 500

    def __init__(self, message="Erro interno.", status_code=None, campo=None, erros=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        # Erros por campo, para o front pintar o input certo sem depender
        # do texto da mensagem: {campo: mensagem}.
        #   - `erros`: dicionário completo (vários campos)
        #   - `campo`: atalho para um campo só -> {campo: message}
        # None quando o erro não pertence a um campo específico.
        self.erros = erros or ({campo: message} if campo else None)


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