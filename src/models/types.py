from src.models import db

BigIntPK = db.BigInteger().with_variant(db.Integer, "sqlite")
