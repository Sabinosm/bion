from src.core.security import ph, aes_encrypt, hmac_sha256, aes_decrypt
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from ..repository import UsuarioRepository
from .service_helpers import (
    CAMPOS_SIMPLES_ATUALIZAVEIS,
    CAMPOS_RESTRITOS_A_ADMIN,
    atributos_atuais,
)
from .service_atualizar import att
from .service_reset import ResetCredenciaisMixin
from src.schemas.schema_usuario import CadastroUsuarioSchema, AtualizacaoUsuarioSchema
from src.models.usuarios import Usuario


def _valida_permissao_edicao(
    self,
    dados: dict,
    solicitante_eh_admin: bool,
    solicitante_eh_super_admin: bool,
    eh_auto_edicao: bool,
    u: "Usuario",
):
        """Valida se o solicitante tem permissão para os campos enviados.

        Cobre estas regras de autorização:
          1. Ninguém que não seja super admin pode alterar um usuário que
             já é admin (comum ou super) -- nem outro admin comum, nem o
             próprio super admin (que de todo modo tem outras proteções
             específicas contra auto-rebaixamento em service.py e
             service_atualizar.py). Um admin comum não pode editar nenhum
             admin, incluindo ele mesmo neste sentido de dados restritos.
          2. Usuários não-admin não podem alterar campos restritos
             (tipo de usuário, registros profissionais).

        ALTERADO (múltiplos admins por empresa): a regra antiga que
        bloqueava só a AUTO-edição de tipo_usuario por um admin foi
        substituída pela checagem mais ampla do item 1 acima -- e pelo
        bloqueio geral de troca de/para admin em service_atualizar.py,
        que já cobre esse caso (ninguém troca tipo_usuario de/para
        "admin" via atualizar(), então a auto-edição de tipo também já
        fica coberta por lá).

        Parâmetros:
            dados: dicionário parcial com os campos a alterar.
            solicitante_eh_admin: se True, o solicitante é admin (comum
                ou super).
            solicitante_eh_super_admin: se True, o solicitante é
                especificamente o super admin da empresa.
            eh_auto_edicao: se True, o solicitante está editando a si mesmo.
            u: instância atual do Usuario, usada para comparar valores.

        Levanta:
            DadosInvalidosError: se alguma das regras de autorização for violada.
        """
        if u.is_admin and not solicitante_eh_super_admin:
            raise DadosInvalidosError(
                "Apenas o administrador principal pode alterar o cadastro de um administrador."
            )

        if not solicitante_eh_admin:
            campos_bloqueados = [c for c in CAMPOS_RESTRITOS_A_ADMIN if c in dados]
            if campos_bloqueados:
                raise DadosInvalidosError(
                    f"Você não tem permissão para alterar: {', '.join(campos_bloqueados)}."
                )

def _valida_troca_tipo(self, tipo_atual: str, novo_tipo: str, tipo_mudou: bool, dados: dict):
        """Valida a troca de tipo profissional (médico <-> enfermeiro).

        ALTERADO (múltiplos admins por empresa): troca de/para "admin"
        NUNCA é permitida por aqui -- virar admin só acontece através de
        criar() (e só o super admin pode fazer isso); um admin existente
        nunca é rebaixado. Essa checagem já é feita antes desta função
        ser chamada, em service_atualizar.py (bloqueio incondicional),
        então aqui só resta validar a troca médico <-> enfermeiro, que é
        a única troca de tipo ainda permitida via atualizar().

        Parâmetros:
            tipo_atual: tipo de usuário antes da atualização.
            novo_tipo: tipo de usuário resultante da atualização.
            tipo_mudou: se True, o tipo de usuário está sendo alterado.
            dados: dicionário parcial com os campos enviados na requisição.

        Levanta:
            DadosInvalidosError: se os atributos exigidos pelo novo tipo
                não estiverem completos.
        """
        if not tipo_mudou:
            return

        if novo_tipo == "medico" and not (dados.get("numero-crm") and dados.get("uf-crm")):
            raise DadosInvalidosError("Troca para médico exige 'numero-crm' e 'uf-crm'.")
        if novo_tipo == "enfermeiro" and not (
            dados.get("numero-coren") and dados.get("uf-coren") and dados.get("especialidade")
        ):
            raise DadosInvalidosError(
                "Troca para enfermeiro exige 'numero-coren', 'uf-coren' e 'especialidade'."
            )
    
def _checar_duplicidade(self, *, cpf_hash=None, email=None, login=None, ignorar_uuid=None):
        """Garante unicidade de CPF, e-mail e login entre usuários.

        Parâmetros:
            cpf_hash: hash do CPF a validar, ou None para pular a checagem.
            email: e-mail a validar, ou None para pular a checagem.
            login: login a validar, ou None para pular a checagem.
            ignorar_uuid: UUID do próprio usuário, para não conflitar
                consigo mesmo em uma atualização.

        Levanta:
            ConflictoError: se algum valor já pertencer a outro usuário.
        """
        checagens = (
            (cpf_hash, self.repo.find_by_cpf_hash, "CPF"),
            (email, self.repo.find_by_email, "E-mail"),
            (login, self.repo.find_by_login, "Login"),
        )
        for valor, buscador, rotulo in checagens:
            if not valor:
                continue
            existente = buscador(valor)
            if existente and getattr(existente, "uuid", None) != ignorar_uuid:
                raise ConflictoError(f"{rotulo} já cadastrado para outro usuário.")