"""service_validacoes.py -- validações de autorização e unicidade do Usuario.

Reúne as checagens que o service aplica antes de alterar um cadastro:
quem pode editar quem, quais campos exigem privilégio, como a função
clínica pode ser trocada, que o cargo de admin não muda por edição e que
CPF, e-mail e login continuam únicos. São funções soltas que recebem o
service como `self` e são anexadas à classe UsuarioService, só para
manter o service principal enxuto.
"""

from src.core.exceptions import ConflictoError, DadosInvalidosError
from .service_helpers import CAMPOS_RESTRITOS_A_ADMIN
from src.models.usuarios import Usuario


def _valida_permissao_edicao(
    self,
    dados: dict,
    solicitante_is_admin: bool,
    solicitante_eh_super_admin: bool,
    u: "Usuario",
):
    """Valida se o solicitante pode editar este usuário e estes campos.

    Regras:
      1. Só o super admin altera o cadastro de um usuário que já é admin
         (comum ou super). Isso vale também para um admin comum editando
         a si mesmo.
      2. Quem não é admin não pode enviar campos restritos
         (CAMPOS_RESTRITOS_A_ADMIN).
      3. Senha nunca é alterada por edição de cadastro, nem pelo próprio
         usuário: a troca é feita em alterar_senha (com step-up) e o
         reset por um admin em resetar_senha_usuario.

    Parâmetros:
        dados: payload parcial com os campos a alterar.
        solicitante_is_admin: se o solicitante é admin (comum ou super).
        solicitante_eh_super_admin: se é especificamente o super admin.
        u: usuário sendo editado.

    Levanta:
        DadosInvalidosError: se alguma regra for violada.
    """
    if u.is_admin and not solicitante_eh_super_admin:
        raise DadosInvalidosError(
            "Apenas o administrador principal pode alterar o cadastro de um administrador."
        )

    if "senha" in dados:
        raise DadosInvalidosError(
            "A senha não pode ser alterada por edição de cadastro. "
            "Use a troca de senha."
        )

    if not solicitante_is_admin:
        campos_bloqueados = [c for c in CAMPOS_RESTRITOS_A_ADMIN if c in dados]
        if campos_bloqueados:
            raise DadosInvalidosError(
                f"Você não tem permissão para alterar: {', '.join(campos_bloqueados)}."
            )


def _valida_troca_tipo(self, papel_atual: str | None, novo_papel: str | None, papel_mudou: bool, dados: dict):
    """Valida a troca de função clínica (médico <-> enfermeiro <-> nenhuma).

    Só olha a função clínica; o cargo de admin é validado por
    _valida_alteracao_admin.

    Parâmetros:
        papel_atual: função antes da atualização ("medico"/"enfermeiro"/None).
        novo_papel: função resultante.
        papel_mudou: se a função está mudando.
        dados: payload da requisição (formato da API, chaves com hífen).

    Levanta:
        DadosInvalidosError: se faltarem os dados exigidos pelo novo papel.
    """
    if not papel_mudou:
        return

    if novo_papel == "medico" and not (dados.get("numero-crm") and dados.get("uf-crm")):
        raise DadosInvalidosError("Troca para médico exige 'numero-crm' e 'uf-crm'.")
    if novo_papel == "enfermeiro" and not (
        dados.get("numero-coren") and dados.get("uf-coren") and dados.get("especialidade")
    ):
        raise DadosInvalidosError(
            "Troca para enfermeiro exige 'numero-coren', 'uf-coren' e 'especialidade'."
        )


def _valida_alteracao_admin(self, admin_mudou: bool):
    """Impede qualquer mudança do cargo de admin por edição de cadastro.

    Nem promover nem rebaixar, para qualquer solicitante, inclusive o
    super admin. Virar admin só acontece na criação.

    Parâmetros:
        admin_mudou: se is_admin está sendo alterado pelo payload.

    Levanta:
        DadosInvalidosError: se admin_mudou for True.
    """
    if admin_mudou:
        raise DadosInvalidosError(
            "O cargo de administrador não pode ser alterado por edição de cadastro."
        )


def _checar_duplicidade(self, *, cpf_hash=None, email=None, login=None, ignorar_uuid=None):
    """Garante unicidade de CPF, e-mail e login entre usuários.

    Parâmetros:
        cpf_hash: hash do CPF a checar, ou None para pular.
        email: e-mail a checar, ou None para pular.
        login: login a checar, ou None para pular.
        ignorar_uuid: UUID do próprio usuário, para não conflitar consigo
            mesmo numa atualização.

    Levanta:
        ConflictoError: se algum valor já pertencer a outro usuário.
    """
    checagens = (
        (cpf_hash, self.repo.find_by_cpf_hash, "CPF"),
        (email, self.repo.find_by_email, "E-mail"),
        (login, self.repo.find_by_user_login, "Login"),
    )
    for valor, buscador, rotulo in checagens:
        if not valor:
            continue
        existente = buscador(valor)
        if existente and getattr(existente, "uuid", None) != ignorar_uuid:
            raise ConflictoError(f"{rotulo} já cadastrado para outro usuário.")