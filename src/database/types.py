"""
Tipo de coluna compartilhado para chaves primarias.

BigInteger e o tipo correto para producao (MySQL, ver .env.example), mas
o SQLite so trata uma coluna como alias de ROWID autoincrementavel quando
o tipo declarado e exatamente INTEGER -- com BigInteger puro, o SQLite
nao gera o autoincrement e qualquer INSERT sem id explicito falha com
"NOT NULL constraint failed". Isso so afeta ambientes de teste (SQLite
em memoria, ver TestingConfig); em MySQL o comportamento e identico ao
BigInteger puro. `with_variant` resolve os dois casos ao mesmo tempo.
"""

from src.database import db

BigIntPK = db.BigInteger().with_variant(db.Integer, "sqlite")
