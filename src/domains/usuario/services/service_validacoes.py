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

def _valida_troca_tipo(self, papel_atual: str | None, novo_papel: str | None, papel_mudou: bool, dados: dict):
        """Valida a troca de função clínica (médico <-> enfermeiro <-> nenhuma).

        ALTERADO (separação admin/papel clínico, assertivo): esta função
        cobria também a troca de/para "admin" através de uma comparação
        de string única. Isso saiu -- eh_admin agora é um eixo
        independente, validado por _valida_alteracao_admin (abaixo).
        Aqui só resta o eixo de função clínica.

        Parâmetros:
            papel_atual: função clínica antes da atualização
                ("medico"/"enfermeiro"/None).
            novo_papel: função clínica resultante da atualização.
            papel_mudou: se True, a função clínica está sendo alterada.
            dados: dicionário parcial com os campos enviados na requisição.

        Levanta:
            DadosInvalidosError: se os atributos exigidos pelo novo
                papel não estiverem completos.
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


def _valida_alteracao_admin(self, eh_admin_atual: bool, novo_eh_admin: bool, admin_mudou: bool):
        """Valida o eixo eh_admin isoladamente — independente da função clínica.

        ADICIONADO (separação admin/papel clínico): mesma regra que
        antes vivia misturada em service_atualizar.py comparando
        tipo_usuario == "admin" -- extraída para função própria porque
        agora é um eixo independente do papel clínico, e precisa da
        mesma checagem incondicional: cargo de admin nunca é alterado
        por edição de cadastro (nem promover, nem rebaixar), para
        qualquer solicitante, inclusive o super admin. Virar admin só
        acontece em criar(); rebaixar um admin nunca é permitido.

        Parâmetros:
            eh_admin_atual: se o usuário já é admin antes da atualização.
            novo_eh_admin: valor de eh_admin resultante da atualização.
            admin_mudou: se True, eh_admin está sendo alterado no payload.

        Levanta:
            DadosInvalidosError: se o payload tentar mudar eh_admin.
        """
        if admin_mudou:
            raise DadosInvalidosError(
                "O cargo de administrador não pode ser alterado por edição de cadastro."
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