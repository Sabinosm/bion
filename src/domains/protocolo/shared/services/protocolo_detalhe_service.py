"""protocolo_detalhe_service.py

Monta, numa única chamada, tudo que a página de detalhe do catálogo precisa
para carregar sozinha (inclusive após F5, via ?uuid=): o detalhe do protocolo,
o resumo com liberação e favoritos do usuário (mesmo DTO dos cards da
listagem) e a versão ativa. Somente leitura: ver um protocolo não é usá-lo,
então qualquer usuário logado pode consultar, liberado ou não.
"""
from src.domains.empresa.empresa_protocolo.empresa_protocolo_repository import EmpresaProtocoloRepository

from ..repositories.protocolo_versao_repository import ProtocoloVersaoRepository
from .protocolo_catalogo_service import ProtocoloCatalogoService


class ProtocoloDetalheService:

    def __init__(self):
        self.svc_catalogo = ProtocoloCatalogoService()
        self.repo_empresa_protocolo = EmpresaProtocoloRepository()
        self.repo_versao = ProtocoloVersaoRepository()

    def obter_detalhe(self, uuid: str, id_empresa: int) -> dict:
        """Retorna {"protocolo", "resumo", "versao_ativa"} do protocolo.

        Raises:
            RecursoNaoEncontradoError: se o UUID não existir.
        """
        protocolo = self.svc_catalogo.buscar_por_uuid(uuid)

        # Resumo no mesmo formato dos cards (liberado_pela_empresa, politica,
        # padrao_institucional, favorito, default_pessoal).
        vinculo = self.repo_empresa_protocolo.find_por_empresa_e_protocolo(id_empresa, protocolo.id)
        linha = (
            protocolo,
            vinculo.ativo if vinculo else None,
            vinculo.politica if vinculo else None,
        )
        resumo = self.svc_catalogo.montar_resumos(id_empresa, [linha])[0]

        return {
            "protocolo": self._montar_detalhe(protocolo),
            "resumo": resumo,
            "versao_ativa": self._montar_versao_ativa(protocolo.id),
        }

    @staticmethod
    def _montar_detalhe(protocolo) -> dict:
        """Dict do protocolo com a explicação renomeada para `explicacao`
        ({o_que_e, quando_usar, como_interpretar}) e as datas em "AAAA-MM-DD"."""
        detalhe = protocolo.to_dict()
        detalhe.pop("explicacao_json", None)
        detalhe["explicacao"] = getattr(protocolo, "explicacao_json", None)
        detalhe["data_vigencia"] = protocolo.data_vigencia.isoformat() if protocolo.data_vigencia else None
        detalhe["data_vigencia_fim"] = (
            protocolo.data_vigencia_fim.isoformat() if protocolo.data_vigencia_fim else None
        )
        return detalhe

    def _montar_versao_ativa(self, id_protocolo_catalogo: int) -> dict | None:
        """Versão de ProtocoloVersao que a execução registra. A página mostra
        esta, com fallback para detalhe["versao_vigente"] quando for None."""
        versao = self.repo_versao.find_vigente(id_protocolo_catalogo)
        if not versao:
            return None
        return {
            "numero_versao": versao.numero_versao,
            "vigente_desde": versao.vigente_desde.isoformat() if versao.vigente_desde else None,
            "status": versao.status,
        }
