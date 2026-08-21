"""
Dominio de Usuarios (profissionais de saude, admins).

Usuario ja estava quase completo no projeto original; mantido. Configuracao
era um stub no original; completado com vinculo 1-para-1 com Usuario e um
JSON livre de preferencias/overrides de protocolo.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class CredencialWebAuthn(db.Model):
    """
    Guarda a CHAVE PÚBLICA de cada dispositivo/autenticador que o usuário
    cadastrou (ex: Face ID do celular, Windows Hello do notebook, Yubikey).
 
    Um mesmo usuário pode ter várias linhas aqui (um por dispositivo).
    A chave PRIVADA nunca existe no servidor — fica só no hardware do usuário.
    """
    
    __tablename__ = 'credencial_webauthn' # Ajuste para o nome real da sua tabela, se necessário

    id_credencial = db.Column(db.BigInteger, primary_key=True)
    id_usuario = db.Column(
        db.BigInteger, db.ForeignKey("usuarios.id_usuario"), nullable=False, index=True
    )
 
    # ID público da credencial, gerado pelo autenticador (base64url)
    credential_id = db.Column(db.String(512), unique=True, nullable=False, index=True)
 
    # Chave pública em bytes (formato COSE) — usada para VERIFICAR assinaturas
    public_key = db.Column(db.LargeBinary, nullable=False)
 
    # Contador anti-replay: incrementa a cada login: se vier um valor menor
    # ou igual ao salvo, pode ser um clone/replay da credencial -> bloquear
    sign_count = db.Column(db.BigInteger, nullable=False, default=0)
 
    # Nome amigável pro usuário identificar o dispositivo (opcional)
    apelido_dispositivo = db.Column(db.String(120), nullable=True)
    
    # Tipo de dispositivo para ajudar nos ícones (ex: 'mobile', 'desktop', 'nfc', 'usb')
    tipo_dispositivo = db.Column(db.String(50), nullable=True)
 
    criado_em = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        """
        Retorna um dicionário formatado para a tela de configurações.
        """
        # Formata a data para o padrão dd/mm/yyyy (verifica se não é nula por segurança)
        data_formatada = self.criado_em.strftime("%d/%m/%Y") if self.criado_em else ""
            
        # Garante um apelido de exemplo padrão caso o usuário não tenha preenchido
        apelido = self.apelido_dispositivo if self.apelido_dispositivo else "Chave de Segurança (WebAuthn)"
            
        # Retorna um tipo padrão caso esteja vazio
        tipo = self.tipo_dispositivo if self.tipo_dispositivo else "desconhecido"

        return {
                "id_credencial": self.id_credencial,
                "apelido": apelido,
                "tipo": tipo,
                "criado_em": data_formatada
            }