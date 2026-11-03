"""proposta.py

Ponto unico que conhece o schema da proposta de prescricao que o projeto ja tem. PropostaPrescricaoIA e o formato exigido da resposta da IA para a conduta (resultado com CID e certeza, medicamentos e exames, todos por uuid do catalogo). Este pacote nao o redefine: apenas o reexporta.
"""
from src.domains.prescricao.schema_prescricoes import PropostaPrescricaoIA, UuidStr

__all__ = ["PropostaPrescricaoIA", "UuidStr"]
