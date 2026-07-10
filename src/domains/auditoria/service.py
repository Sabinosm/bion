"""
Regras de negocio do dominio Auditoria.

Os logs sao gravados de forma append-only (sem update/delete, ver
repository.py) para atender ao requisito de imutabilidade citado nas
memorias do projeto (trilha de auditoria LGPD).
"""

from datetime import datetime, timezone

from src.core.exceptions import RecursoNaoEncontradoError, PermissaoNegadaError
from .repository import LogAcessoRepository, LogAlteracaoRepository


class AuditoriaService:

    def __init__(self):
        self.acesso_repo = LogAcessoRepository()
        self.alteracao_repo = LogAlteracaoRepository()

    def registrar_acesso(self, id_usuario: int, recurso: str, operacao: str,
                          ip_origem: str, resultado: str = "sucesso", uuid_paciente: str = None):
        from src.models.auditoria.log_acesso import LogAcesso
        log = LogAcesso(
            id_usuario=id_usuario,
            recurso_acessado=recurso,
            operacao=operacao,
            data_hora=datetime.now(timezone.utc),
            ip_origem=ip_origem,
            resultado=resultado,
            uuid_paciente=uuid_paciente,
        )
        return self.acesso_repo.save(log)

    def registrar_alteracao(self, tabela_origem: str, id_registro: int, uuid_registro: str,
                             operacao: str, id_usuario: int = None, campo_alterado: str = None,
                             valor_anterior: str = None, valor_novo: str = None,
                             ip_origem: str = None, justificativa: str = None):
        from src.models.auditoria.log_alteracao import LogAlteracao
        log = LogAlteracao(
            tabela_origem=tabela_origem,
            id_registro=id_registro,
            uuid_registro=uuid_registro,
            operacao=operacao,
            campo_alterado=campo_alterado,
            valor_anterior=valor_anterior,
            valor_novo=valor_novo,
            alterado_por=id_usuario,
            ip_origem=ip_origem,
            justificativa=justificativa,
        )
        return self.alteracao_repo.save(log)

    def listar_acessos(self, id_usuario_alvo: int = None):
        if id_usuario_alvo:
            return self.acesso_repo.find_por_usuario(id_usuario_alvo)
        return self.acesso_repo.find_all()

    def listar_alteracoes(self, tabela_origem: str = None, uuid_registro: str = None):
        if tabela_origem and uuid_registro:
            return self.alteracao_repo.find_por_registro(tabela_origem, uuid_registro)
        return self.alteracao_repo.find_all()

    def excluir(self, *args, **kwargs):
        raise PermissaoNegadaError("Registros de auditoria são imutáveis e não podem ser excluídos.")
