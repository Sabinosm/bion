"""Fluxo COM IA: transforma a proposta validada da IA em um ResultadoPrescricao
em rascunho, ligado ao médico da sessão. Tudo em uma única transação."""

from src.models import db
from resultado_prescricao.resultado_prescricao_service import ResultadoPrescricaoService
from .prescricao_service import PrescricaoService
from prescricao_exame.prescricao_exame_service import PrescricaoExameService
from .schema_prescricoes import PropostaPrescricaoIA


class PrescricaoIAService:
    def __init__(self):
        self.resultado_svc = ResultadoPrescricaoService()
        self.prescricao_svc = PrescricaoService()
        self.exame_svc = PrescricaoExameService()

    def registrar_proposta(self, uuid_atendimento: str, proposta: PropostaPrescricaoIA,
                           id_usuario: int, id_output: int):
        """Retorna o ResultadoPrescricao criado, ou None se a IA não recomendou nada
        (nesse caso o registro fica só no Output_bion).

        Use: proposta = PropostaPrescricaoIA.model_validate(json_da_ia)
             id_usuario = get_id_usuario_sessao()
        Se algum item for inválido (ex.: id inexistente no catálogo), nada é salvo.
        """
        if proposta.sem_recomendacao:
            return None
        try:
            resultado = self.resultado_svc.registrar_resultado(
                uuid_atendimento, proposta.resultado, id_usuario, id_output=id_output, commit=False
            )
            for m in proposta.medicamentos:
                self.prescricao_svc.incluir(resultado, m, origem="bion_ia",
                                            id_output_origem=id_output, commit=False)
            for e in proposta.exames:
                self.exame_svc.incluir(resultado, e, origem="bion_ia",
                                       id_output_origem=id_output, commit=False)
            db.session.commit()
            return resultado
        except Exception:
            db.session.rollback()
            raise