"""Detalhe de um protocolo para a página adminCatalogosDetalhe.

Junta numa chamada só o que a página precisa para carregar sozinha (inclusive
depois de F5, por ?uuid=): o detalhe do catálogo, o resumo com liberação e
favoritos do usuário (o MESMO DTO dos cards da listagem) e a versão ativa.

Local: src/domains/protocolo/ (ao lado de protocolo_catalogo_controller.py).
Somente leitura -- ver não é usar: qualquer usuário logado, liberado ou não.
"""

from src.domains.empresa.empresa_protocolo.empresa_protocolo_service import EmpresaProtocoloRepository
from .protocolo_catalogo_service import ProtocoloCatalogoService
from ..repositories.protocolo_versao_repository import ProtocoloVersaoRepository


class ProtocoloDetalheService:

    def __init__(self):
        self.svc_catalogo = ProtocoloCatalogoService()
        self.repo_empresa_protocolo = EmpresaProtocoloRepository()
        self.repo_versao = ProtocoloVersaoRepository()

    def obter_detalhe(self, uuid: str, id_empresa: int) -> dict:
        protocolo = self.svc_catalogo.buscar_por_uuid(uuid)  # 404 se não existir

        # Resumo no mesmo formato dos cards (liberado_pela_empresa, politica,
        # padrao_institucional, favorito, default_pessoal).
        vinculo = self.repo_empresa_protocolo.find_por_empresa_e_protocolo(id_empresa, protocolo.id)
        linha = (protocolo,
                 vinculo.ativo if vinculo else None,
                 vinculo.politica if vinculo else None)
        resumo = self.svc_catalogo._montar_resumos(id_empresa, [linha])[0]

        # Detalhe: explicação lida direto do model, renomeada para `explicacao`
        # ({o_que_e, quando_usar, como_interpretar}). Datas viram "AAAA-MM-DD".
        detalhe = protocolo.to_dict()
        detalhe.pop("explicacao_json", None)
        detalhe["explicacao"] = getattr(protocolo, "explicacao_json", None)
        detalhe["data_vigencia"] = protocolo.data_vigencia.isoformat() if protocolo.data_vigencia else None
        detalhe["data_vigencia_fim"] = protocolo.data_vigencia_fim.isoformat() if protocolo.data_vigencia_fim else None

        # Versão ativa de ProtocoloVersao (a que a execução registra). O canto da
        # página mostra esta, com fallback para detalhe["versao_vigente"].
        versao = self.repo_versao.find_vigente(protocolo.id)
        versao_ativa = None
        if versao:
            versao_ativa = {
                "numero_versao": versao.numero_versao,
                "vigente_desde": versao.vigente_desde.isoformat() if versao.vigente_desde else None,
                "status": versao.status,
            }

        return {"protocolo": detalhe, "resumo": resumo, "versao_ativa": versao_ativa}