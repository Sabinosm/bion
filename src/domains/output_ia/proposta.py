"""Unico ponto que conhece o schema da proposta que o projeto JA tem.

PropostaPrescricaoIA e o formato exigido da resposta da IA para a conduta:
resultado (CID + certeza + tipo), medicamentos e exames, todos por uuid do
catalogo. Este pacote NAO o redefine: embrulha.

>>> AJUSTE O IMPORT ABAIXO para o caminho real do seu schema_prescricoes
>>> (ex.: from src.domains.prescricao.schema_prescricoes import PropostaPrescricaoIA).
"""
from src.domains.prescricao.schema_prescricoes import PropostaPrescricaoIA, UuidStr

__all__ = ["PropostaPrescricaoIA", "UuidStr"]