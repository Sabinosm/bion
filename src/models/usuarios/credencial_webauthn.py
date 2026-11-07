from src.models import db


class CredencialWebAuthn(db.Model):
    __tablename__ = "credencial_webauthn"

    id_credencial = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    id_usuario = db.Column(
        db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False, index=True
    )
    credential_id = db.Column(db.String(512), unique=True, nullable=False, index=True)
    public_key = db.Column(db.LargeBinary, nullable=False)
    sign_count = db.Column(db.BigInteger, nullable=False, default=0)
    apelido_dispositivo = db.Column(db.String(120), nullable=True)
    tipo_dispositivo = db.Column(db.String(50), nullable=True)
    criado_em = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        data_formatada = self.criado_em.strftime("%d/%m/%Y") if self.criado_em else ""
        apelido = self.apelido_dispositivo or "Chave de Seguranca (WebAuthn)"
        tipo = self.tipo_dispositivo or "desconhecido"

        return {
            "id_credencial": self.id_credencial,
            "apelido": apelido,
            "tipo": tipo,
            "criado_em": data_formatada,
        }
