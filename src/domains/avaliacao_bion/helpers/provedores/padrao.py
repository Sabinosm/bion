"""Estrategias sem fornecedor: 'indisponivel' (padrao seguro) e 'falso' (desenvolvimento)."""
from ..cliente import ClienteIAFalso, ClienteIAIndisponivel
from ..fabrica import provedor

provedor("indisponivel")(ClienteIAIndisponivel)
provedor("falso")(ClienteIAFalso)
