# shared/repositories/protocolo_composicao_repository.py
from sqlalchemy.orm import selectinload, joinedload
from src.models.protocolos import (
    ProtocoloComposicao, ModuloVersao, ModuloVersaoCampo, ProtocoloComposicaoConfig,
)

class ProtocoloComposicaoRepository:

    def carregar_composicao(self, id_protocolo_versao: int):
        """Traz a árvore inteira: composição -> versão do módulo -> módulo,
        campos e variáveis. Uma ida ao banco por nível (selectinload), sem N+1."""
        return (
            ProtocoloComposicao.query
            .filter_by(id_protocolo_versao=id_protocolo_versao)
            .options(
                joinedload(ProtocoloComposicao.modulo_versao)
                    .joinedload(ModuloVersao.modulo),
                joinedload(ProtocoloComposicao.modulo_versao)
                    .selectinload(ModuloVersao.campos)
                    .joinedload(ModuloVersaoCampo.variavel),
            )
            .order_by(ProtocoloComposicao.ordem)
            .all()
        )

    def carregar_config(self, id_protocolo_versao: int):
        return ProtocoloComposicaoConfig.query.get(id_protocolo_versao)