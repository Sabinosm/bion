"""padrao.py

Estratégias sem fornecedor: indisponível (padrão seguro) e falso (desenvolvimento e testes).
"""
from ..cliente import ClienteIAFalso, ClienteIAIndisponivel
from ..fabrica import provedor

provedor("indisponivel")(ClienteIAIndisponivel)
provedor("falso")(ClienteIAFalso)
