from src.core.security import ph, aes_encrypt, hmac_sha256, aes_decrypt
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from ..repository import UsuarioRepository
from .service_helpers import (
    CAMPOS_SIMPLES_ATUALIZAVEIS,
    CAMPOS_RESTRITOS_A_ADMIN,
    atributos_atuais,
    monta_atributos_json,
)
from .service_atualizar import att
from .service_reset import ResetCredenciaisMixin
from src.schemas.schema_usuario import CadastroUsuarioSchema, AtualizacaoUsuarioSchema
from src.models.usuarios import Usuario


def _valida_permissao_edicao(self, dados: dict, solicitante_eh_admin: bool, eh_auto_edicao: bool, u: "Usuario"):
        """Valida se o solicitante tem permissão para os campos enviados.

        Cobre duas regras de autorização:
          1. Usuários não-admin não podem alterar campos restritos
             (tipo de usuário, registros profissionais).
          2. Um admin não pode alterar seu próprio `tipo_usuario`, mesmo
             que o campo não esteja bloqueado para ele.

        Parâmetros:
            dados: dicionário parcial com os campos a alterar.
            solicitante_eh_admin: se True, o solicitante pode alterar
                campos restritos.
            eh_auto_edicao: se True, o solicitante está editando a si mesmo.
            u: instância atual do Usuario, usada para comparar valores.

        Levanta:
            DadosInvalidosError: se alguma das regras de autorização for violada.
        """
        if not solicitante_eh_admin:
            campos_bloqueados = [c for c in CAMPOS_RESTRITOS_A_ADMIN if c in dados]
            if campos_bloqueados:
                raise DadosInvalidosError(
                    f"Você não tem permissão para alterar: {', '.join(campos_bloqueados)}."
                )

        if eh_auto_edicao and "tipo_usuario" in dados and dados["tipo_usuario"] != u.tipo_usuario:
            raise DadosInvalidosError("Você não pode alterar seu próprio tipo de usuário.")

def _valida_troca_tipo(self, novo_tipo: str, tipo_mudou: bool, dados: dict):
        """Valida se os atributos profissionais exigidos foram enviados.

        Mudar o `tipo_usuario` para médico ou enfermeiro exige que os
        respectivos atributos profissionais completos venham junto no
        mesmo payload de atualização.

        Parâmetros:
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