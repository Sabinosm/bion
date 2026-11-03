"""prescricao_ia_service.py

Fluxo COM IA: transforma a proposta validada da IA em um ResultadoPrescricao em
rascunho, ligado ao médico da sessão, com os medicamentos e exames sugeridos.
Tudo em uma única transação.

A IA referencia os catálogos pelo UUID público. Se algum item for inválido (UUID
inexistente, item repetido), nada é salvo. Também nada é salvo (409) se o
atendimento já não está em andamento ou se há rascunho do médico: o worker não
escreve em atendimento finalizado ou cancelado, nem por cima do que o médico
está editando. Proposta sem medicamentos e sem exames não gera resultado: o
registro fica só no envio à IA. Os alertas de interação ficam disponíveis na
rota de alertas do resultado.
"""

from .resultado_prescricao.resultado_prescricao_repository import ResultadoPrescricaoRepository
from .resultado_prescricao.resultado_prescricao_service import ResultadoPrescricaoService
from .prescricao_service import PrescricaoService
from .prescricao_exame.prescricao_exame_service import PrescricaoExameService
from .schema_prescricoes import PropostaPrescricaoIA


class PrescricaoIAService:
    def __init__(self):
        self.resultado_repo = ResultadoPrescricaoRepository()  # só para controlar a transação única
        self.resultado_svc = ResultadoPrescricaoService()
        self.prescricao_svc = PrescricaoService()
        self.exame_svc = PrescricaoExameService()

    def registrar_proposta(self, uuid_atendimento: str, proposta: PropostaPrescricaoIA,
                           id_usuario: int, id_output: int, id_empresa: int):
        """Retorna o ResultadoPrescricao criado, ou None se a IA não recomendou nada.

        Uso: proposta = PropostaPrescricaoIA.model_validate(json_da_ia);
             id_usuario = get_id_usuario_sessao().

        Raises:
            RecursoNaoEncontradoError: atendimento (ou item de catálogo) inexistente.
            PermissaoNegadaError: o usuário não é o profissional do atendimento.
            ConflictoError: atendimento fora de andamento, rascunho do médico em curso,
                ou item repetido.
        """
        if proposta.sem_recomendacao:
            return None
        try:
            resultado = self.resultado_svc.registrar_resultado(
                uuid_atendimento, proposta.resultado, id_empresa, id_usuario, id_output=id_output, commit=False
            )
            for m in proposta.medicamentos:
                self.prescricao_svc.incluir(resultado, m, origem="bion_ia",
                                            id_output_origem=id_output, commit=False)
            for e in proposta.exames:
                self.exame_svc.incluir(resultado, e, origem="bion_ia",
                                       id_output_origem=id_output, commit=False)
            self.resultado_repo.confirmar()
            return resultado
        except Exception:
            self.resultado_repo.rollback()
            raise
