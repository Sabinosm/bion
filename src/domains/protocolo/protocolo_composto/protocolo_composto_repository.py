"""protocolo_composto_repository.py

Acesso a dados da composição de um protocolo composto: os módulos que o
compõem (com versão do módulo, campos e variáveis) e a configuração de
agregação/gatilhos da versão do protocolo. Monta também o envelope de dado
bruto que a estratégia do protocolo composto espera.
"""
from sqlalchemy.orm import joinedload, selectinload

from src.models.protocolos import (
    ModuloVersao,
    ModuloVersaoCampo,
    ProtocoloComposicao,
    ProtocoloComposicaoConfig,
)


class ProtocoloComposicaoRepository:

    def carregar_composicao(self, id_protocolo_versao: int) -> list[ProtocoloComposicao]:
        """Traz a árvore inteira da composição, ordenada por `ordem`: versão do
        módulo, módulo, campos e variáveis, evitando N+1."""
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

    def carregar_config(self, id_protocolo_versao: int) -> ProtocoloComposicaoConfig | None:
        """Configuração de agregação e gatilhos da versão (None se não houver)."""
        return ProtocoloComposicaoConfig.query.get(id_protocolo_versao)

    def carregar_dado_bruto(self, versao) -> dict:
        """Envelope que `ProtocoloCompostoStrategy.carregar_estrutura` espera:
        {"versao", "linhas", "config"}."""
        return {
            "versao": versao,
            "linhas": self.carregar_composicao(versao.id),
            "config": self.carregar_config(versao.id),
        }
