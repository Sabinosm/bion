"""
CredencialWebAuthn — chave publica de cada dispositivo/autenticador
(Face ID, Windows Hello, Yubikey etc.) cadastrado pelo usuario como
segundo fator. Um usuario pode ter varias linhas, uma por dispositivo.
A chave privada nunca existe no servidor, fica so no hardware do usuario.
"""

from src.models import db


class CredencialWebAuthn(db.Model):
    __tablename__ = 'credencial_webauthn'

    id_credencial = db.Column(db.BigInteger, primary_key=True)
    id_usuario = db.Column(
        db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False, index=True
    )

    # ID publico da credencial, gerado pelo autenticador (base64url)
    credential_id = db.Column(db.String(512), unique=True, nullable=False, index=True)

    # Chave publica em bytes (formato COSE), usada para verificar assinaturas
    public_key = db.Column(db.LargeBinary, nullable=False)

    # Contador anti-replay: incrementa a cada login; um valor recebido
    # menor ou igual ao salvo indica possivel clone/replay da credencial
    sign_count = db.Column(db.BigInteger, nullable=False, default=0)

    apelido_dispositivo = db.Column(db.String(120), nullable=True)
    tipo_dispositivo = db.Column(db.String(50), nullable=True)  # ex: 'mobile', 'desktop', 'nfc', 'usb'

    criado_em = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        """Representacao formatada para a tela de configuracoes."""
        data_formatada = self.criado_em.strftime("%d/%m/%Y") if self.criado_em else ""
        apelido = self.apelido_dispositivo or "Chave de Seguranca (WebAuthn)"
        tipo = self.tipo_dispositivo or "desconhecido"

        return {
            "id_credencial": self.id_credencial,
            "apelido": apelido,
            "tipo": tipo,
            "criado_em": data_formatada,
        }