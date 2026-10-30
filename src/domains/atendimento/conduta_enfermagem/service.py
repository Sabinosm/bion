"""service.py

Regras de negócio da conduta de enfermagem: registro opcional em que o
profissional detalha o que fez durante a triagem. Ele NÃO entra no gate do
binário e não bloqueia a finalização do atendimento.

A escrita passa pela checagem comum de escrita clínica (o Atendimento é da
empresa e do paciente do caminho, só o dono escreve, enfermeiro e médico podem,
o paciente não tem óbito) mais regras próprias: o Atendimento precisa estar em
andamento (conferido de novo depois de travar a linha, para não gravar numa
triagem finalizada no meio da requisição) e o tipo precisa permitir conduta
(hoje só a triagem). O registro é insert-only: não há edição nem exclusão, e a
correção é uma nova conduta. A função de quem escreveu (médico ou enfermeiro)
vem da sessão e fica gravada na conduta.

O service nunca lê a sessão: o controller monta o AutorClinico.
"""

from src.core.exceptions import (
    RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError,
)
from src.domains.atendimento.contexto_clinico_service import AutorClinico, ContextoClinicoService
from src.domains.atendimento.repository import AtendimentoRepository
from src.domains.consulta.repository import ConsultaRepository
from src.models.clinico.conduta_enfermagem import CondutaEnfermagem
from .repository import CondutaEnfermagemRepository

TIPOS_COM_CONDUTA = ("triagem",)


class CondutaEnfermagemService:

    def __init__(self):
        self.repo = CondutaEnfermagemRepository()
        self.atendimento_repo = AtendimentoRepository()
        self.consulta_repo = ConsultaRepository()
        self.contexto = ContextoClinicoService()

    def registrar(self, uuid_atendimento: str, uuid_paciente: str, dados: dict,
                  autor: AutorClinico, commit: bool = True) -> CondutaEnfermagem:
        """
        Registra uma conduta de enfermagem no Atendimento (insert-only).

        `dados` é o corpo já validado pelo schema (descricao_conduta e, opcional,
        uuid_protocolo_catalogo). Com commit=False a conduta fica só em flush, para o
        controller comitar junto com o log de auditoria.

        Raises:
            RecursoNaoEncontradoError: Atendimento ou paciente inexistente na empresa.
            PermissaoNegadaError: não é o dono do Atendimento.
            ConflictoError: Atendimento de outro paciente; não está em andamento; tipo sem
                conduta (não é triagem); paciente sem condição de atendimento (óbito).
            DadosInvalidosError: protocolo do catálogo inexistente.
        """
        atendimento = self.contexto.exigir_escrita(uuid_atendimento, uuid_paciente, autor).atendimento
        if atendimento.tipo_atendimento not in TIPOS_COM_CONDUTA:
            raise ConflictoError("Conduta de enfermagem só é registrada em atendimento de triagem.")

        id_protocolo = None
        uuid_protocolo = dados.get("uuid_protocolo_catalogo")
        if uuid_protocolo:
            protocolo = self.repo.find_protocolo_por_uuid(uuid_protocolo)
            if not protocolo:
                raise DadosInvalidosError(
                    "Protocolo não encontrado.", erros={"uuid_protocolo_catalogo": "protocolo não encontrado."}
                )
            id_protocolo = protocolo.id

        try:
            self.atendimento_repo.travar(atendimento)
            if atendimento.status != "em-andamento":
                raise ConflictoError("O atendimento não está em andamento.")
            conduta = CondutaEnfermagem(
                id_atendimento=atendimento.id,
                id_protocolo_catalogo=id_protocolo,
                descricao_conduta=dados["descricao_conduta"],
                realizado_por=autor.id_usuario,
                funcao_clinica=autor.funcao_clinica,
            )
            self.repo.save(conduta, commit=commit)
            return conduta
        except Exception:
            self.repo.rollback()
            raise

    def listar_por_atendimento(self, uuid_atendimento: str, id_empresa: int):
        """Lista as condutas de um Atendimento da empresa, em ordem cronológica.
        404 igual para 'não existe' e 'é de outra empresa'."""
        atendimento = self.atendimento_repo.find_by_uuid(uuid_atendimento, id_empresa)
        if not atendimento:
            raise RecursoNaoEncontradoError(f"Atendimento não encontrado: {uuid_atendimento}")
        return self.repo.find_por_atendimento(atendimento.id)

    def listar_por_consulta(self, uuid_consulta: str, id_empresa: int):
        """Lista as condutas de todos os Atendimentos de uma Consulta da empresa, em ordem
        cronológica: é como o médico lê, na avaliação, o que a triagem fez."""
        consulta = self.consulta_repo.find_by_uuid(uuid_consulta, id_empresa)
        if not consulta:
            raise RecursoNaoEncontradoError(f"Consulta não encontrada: {uuid_consulta}")
        return self.repo.find_por_consulta(consulta.id)
