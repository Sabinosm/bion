"""
Dominio de Usuarios (profissionais de saude, admins).

ALTERADO (migração FHIR, Opção B confirmada):
- tipo_usuario e atributos_profissionais_json SAÍRAM daqui.
- is_admin (bool) entra no lugar de tipo_usuario == 'admin'.
- papel_ativo() é o novo ponto central de acesso ao papel profissional
  (substitui a leitura direta de tipo_usuario em toda a aplicação).
- is_medico()/is_enfermeiro()/is_admin() MANTIDOS como método, mas agora
  delegam para papel_ativo() — qualquer código que já chamava esses
  métodos continua funcionando sem alteração.

ALTERADO (múltiplos admins por empresa):
- Antes só existia 1 admin por empresa (o criado junto com a empresa em
  Empresa.cadastrar_com_admin). Agora uma empresa pode ter vários admins.
- is_super_admin (bool) foi adicionado para distinguir o admin "fundador"
  (criado junto com a empresa) dos demais admins criados depois por ele.
  Só o super admin pode criar novos admins e só ele pode alterar
  (editar/desativar/ativar) outro admin -- um admin comum não pode
  mexer em nenhum admin, nem nele mesmo nesse sentido, nem em outro.
  O super admin em si nunca pode ser rebaixado/desativado, por ninguém,
  nem por ele mesmo. Ver service.py, service_atualizar.py e
  service_validacoes.py para as regras completas.
- Default False: só nasce True dentro de Empresa.cadastrar_com_admin,
  que é o único fluxo que cria o primeiro admin de uma empresa nova.
"""

from datetime import datetime, timezone
import uuid as _uuid

from src.models import db
from src.models.types import BigIntPK


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column("id_usuario", BigIntPK, primary_key=True, autoincrement=True)
    uuid = db.Column("uuid_usuario", db.String(36), unique=True, nullable=False,
                      default=lambda: str(_uuid.uuid4()))
    id_empresa = db.Column(db.BigInteger, db.ForeignKey("empresas.id_empresa"), nullable=False)
    google_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    nome_completo = db.Column(db.String(255), nullable=False)
    cpf = db.Column(db.String(500), nullable=False)  # AES-256-GCM (valor exibível)
    email = db.Column(db.String(255), unique=True, nullable=False)
    telefone = db.Column(db.String(50))
    user_login = db.Column(db.String(100), unique=True)

    # tipo_usuario REMOVIDO — ver papel_ativo() abaixo
    is_admin = db.Column("is_admin", db.Boolean, nullable=False, default=False)

    # ADICIONADO: distingue o admin fundador (único com poder de criar/
    # alterar outros admins) dos demais admins de uma mesma empresa.
    # Só é True quando setado explicitamente em Empresa.cadastrar_com_admin;
    # todo outro fluxo de criação (inclusive criar outro admin) deixa
    # False por default.
    is_super_admin = db.Column("is_super_admin", db.Boolean, nullable=False, default=False)

    status = db.Column(db.Enum("ativo", "inativo", "pendente"),
                        nullable=False, default="pendente")
    # atributos_profissionais_json REMOVIDO — ver PapelProfissional
    hash_senha = db.Column(db.String(255), nullable=True)  # Argon2id
    onboarding_pendente = db.Column(db.Boolean, default=True, nullable=False)
    ultimo_acesso = db.Column(db.DateTime(timezone=True))
    criado_em = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc), nullable=False)
    cpf_hash = db.Column(db.String(255), nullable=False)

    empresa = db.relationship("Empresa", back_populates="usuarios")
    configuracao = db.relationship("Configuracao", back_populates="usuario",
                                    uselist=False, cascade="all, delete-orphan")
    papeis = db.relationship("PapelProfissional", back_populates="usuario",
                              cascade="all, delete-orphan")

    # -----------------------------------------------------------------
    # Ponto central de acesso ao papel — substitui a leitura direta de
    # tipo_usuario em todo o resto do código. Usuário só tem 1 papel
    # profissional ativo por vez (garantido pela UNIQUE KEY no banco:
    # um médico OU um enfermeiro, nunca os dois — ajustar se isso mudar).
    # -----------------------------------------------------------------
    def papel_ativo(self):
        """Retorna a instância de PapelProfissional ativa, ou None (ex: admin puro)."""
        return next((p for p in self.papeis if p.ativo), None)

    @property
    def funcao_clinica(self):
        """
        Substitui a antiga property/coluna tipo_usuario.

        DECISÃO (assertiva, sem alias de compatibilidade): esta property
        reflete SÓ o papel clínico (medico/enfermeiro/None). Nunca
        retorna "admin" — nem para admin puro, sem PapelProfissional.
        is_admin é a ÚNICA fonte de verdade para saber se alguém é
        administrador; funcao_clinica responde a uma pergunta diferente
        (qual profissão, se houver) e as duas são consultadas
        separadamente, nunca uma no lugar da outra.

        Um usuário pode ter is_admin=True e funcao_clinica="medico" ao
        mesmo tempo (admin que também atende) — as duas dimensões são
        ortogonais por design.

        Não é coluna do banco — NÃO pode aparecer em filtros de query,
        tipo `Usuario.query.filter_by(funcao_clinica="medico")`. Ver
        repository.py: find_by_tipo_papel (join com PapelProfissional)
        e find_admins (filtro por is_admin).
        """
        papel = self.papel_ativo()
        return papel.tipo_papel if papel else None

    def is_medico(self):
        papel = self.papel_ativo()
        return bool(papel and papel.tipo_papel == "medico")

    def is_enfermeiro(self):
        papel = self.papel_ativo()
        return bool(papel and papel.tipo_papel == "enfermeiro")

    def to_dict(self, incluir_sensiveis=False):
        """
        ALTERADO (mudança de contrato de API, assertiva/sem transição):
        a chave "tipo_usuario" SAIU da resposta. No lugar entram duas
        chaves independentes:
          - "funcao_clinica": "medico" | "enfermeiro" | None
          - "is_admin": bool
        Um usuário pode ter is_admin=True e funcao_clinica="medico" ao
        mesmo tempo. Front precisa ser atualizado para ler os dois
        campos separadamente — não existe mais um único campo que
        resuma "o que este usuário é".
        """
        papel = self.papel_ativo()
        d = {
            "uuid": self.uuid,
            "nome_completo": self.nome_completo,
            "email": self.email,
            "telefone": self.telefone,
            "user_login": self.user_login,
            "funcao_clinica": self.funcao_clinica,
            "is_admin": self.is_admin,
            "is_super_admin": self.is_super_admin,
            "status": self.status,
            "ultimo_acesso": self.ultimo_acesso.isoformat() if self.ultimo_acesso else None,
            "id_empresa": self.id_empresa,
        }
        if incluir_sensiveis:
            from src.core.security import aes_decrypt
            d["cpf"] = aes_decrypt(self.cpf)
            d["atributos_profissionais"] = papel.to_dict() if papel else None
        return d
    
    def to_dict_few(self):
        """
        ALTERADO: "tipo_usuario" saiu, "funcao_clinica" entra no lugar.
        "is_admin" já existia aqui (não precisou de mudança) — agora as
        duas chaves juntas descrevem o usuário sem ambiguidade: front
        pode ter is_admin=True e funcao_clinica="medico" no mesmo item.
        """
        d = {
                    "uuid": self.uuid,
                    "nome_completo": self.nome_completo,
                    "email": self.email,
                    "funcao_clinica": self.funcao_clinica,
                    "status": self.status,
                    # ADICIONADO (múltiplos admins por empresa): a listagem
                    # agora pode incluir admins comuns (ver
                    # repository.find_all_param) -- o front precisa saber
                    # que o item é admin para desenhar o card certo e para
                    # decidir se mostra ações de gerenciamento (só o super
                    # admin pode agir sobre outro admin). is_super_admin
                    # nunca aparece aqui porque find_all_param já exclui
                    # o super admin da listagem.
                    "is_admin": self.is_admin,
             }
        return d