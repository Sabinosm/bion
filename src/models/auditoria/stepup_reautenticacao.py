"""
Dominio de Auditoria -- estado intermediário do step-up alternativo.

Complementa StepUpToken (em step_up.py) -- este model aqui não é o
token final de confirmação, é o estado intermediário do fluxo
alternativo "senha + Google", usado só por quem não tem nenhuma
credencial WebAuthn cadastrada. Ver src/domains/auth/step_up.py para
o fluxo completo.

Por que uma tabela e não a sessão Flask
------------------------------------------
O fluxo atravessa um redirect real de navegador para o Google e volta
em uma rota de callback separada -- não dá pra garantir que o mesmo
cookie de sessão está presente nas duas pontas (aba diferente,
navegador limpando cookie de terceiros durante o redirect, etc.).
Persistir no banco, como já é feito para StepUpToken, torna o fluxo
robusto a isso e mantém auditável quando cada etapa foi confirmada.
"""

from datetime import datetime, timezone

from src.models import db
from src.models.types import BigIntPK


class StepUpReautenticacao(db.Model):
    """Estado intermediário do fluxo de step-up via senha + Google.

    Uso único e de vida curta -- assim que o callback do Google
    confirma a segunda etapa, o registro é apagado e um StepUpToken
    normal é emitido em seu lugar (mesmo formato usado pelo fluxo de
    WebAuthn), para que `requer_confirmacao_recente` não precise saber
    qual dos dois métodos foi usado.
    """

    __tablename__ = "stepup_reautenticacao"

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    id_usuario = db.Column(db.BigInteger, db.ForeignKey("usuarios.id_usuario"),
                            nullable=False, index=True)
    acao = db.Column(db.String(100), nullable=False)

    # Preenchido em /stepup/senha/confirmar. Enquanto False, o
    # callback do Google (etapa 2) não pode concluir o fluxo -- evita
    # que alguém pule direto para "voltar do Google" sem antes provar
    # a senha.
    senha_confirmada = db.Column(db.Boolean, nullable=False, default=False)

    # Nonce de correlação enviado como `state` no redirect ao Google e
    # conferido no callback -- previne que o callback seja acionado a
    # partir de um registro de reautenticação diferente do que
    # iniciou o redirect (equivalente ao `state` padrão do OAuth,
    # aqui usado para amarrar o registro certo, não só CSRF genérico).
    state = db.Column(db.String(64), unique=True, nullable=False)

    expira_em = db.Column(db.DateTime(timezone=True), nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)

    def expirado(self):
        return datetime.now(timezone.utc) > self.expira_em

    def __repr__(self):
        return f"<StepUpReautenticacao usuario={self.id_usuario} acao={self.acao}>"