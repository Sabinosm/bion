"""
Regras de negocio do dominio Usuario.

Mantidos `criar` e `desativar` do original, e adicionados `atualizar` e
`ativar` -- o controller original tinha uma rota GET /editar (so
renderizava o form) sem nenhum POST correspondente no service; como
service e controller foram unificados, o metodo de update precisava
existir de fato.

Este arquivo foi dividido em 3 para reduzir o tamanho:
  - service_helpers.py  -> funcoes puras de apoio + constantes
  - service_reset.py    -> mixin com reset_2fa / reset_total
  - service.py (este)   -> UsuarioService com o CRUD principal
"""

from src.core.security import ph, aes_encrypt, hmac_sha256, aes_decrypt
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from .repository import UsuarioRepository
from .service_helpers import (
    CAMPOS_SIMPLES_ATUALIZAVEIS,
    CAMPOS_RESTRITOS_A_ADMIN,
    atributos_atuais,
    monta_atributos_json,
)
from .service_reset import ResetCredenciaisMixin
from ...schemas.schema_usuario import CadastroUsuarioSchema, AtualizacaoUsuarioSchema
from src.database.usuarios import Usuario


class UsuarioService(ResetCredenciaisMixin):

    def __init__(self):
        self.repo = UsuarioRepository()

    def buscar_por_uuid(self, uuid: str):
        u = self.repo.find_by_uuid(uuid)
        if not u:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado: {uuid}")
        return u

    def listar(self, id_empresa):
        return self.repo.find_all(id_empresa)

    def _checar_duplicidade(self, *, cpf_hash=None, email=None, login=None, ignorar_uuid=None):
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

    def criar(self, id_empresa, dados: dict, commitar: bool = True):
        try:
            schema = CadastroUsuarioSchema(**dados)
        except Exception as e:
            raise DadosInvalidosError(f"Erro de validação: {e}") from e

        cpf_hash = hmac_sha256(schema.cpf)
        self._checar_duplicidade(cpf_hash=cpf_hash, email=schema.email, login=schema.user_login)

        u = Usuario(
            id_empresa=id_empresa,
            nome_completo=schema.nome_completo,
            cpf=aes_encrypt(schema.cpf),
            cpf_hash=cpf_hash,
            email=schema.email,
            telefone=schema.telefone,
            user_login=schema.user_login,
            tipo_usuario=schema.tipo_usuario,
            atributos_profissionais_json=monta_atributos_json(schema),
        )
        return self.repo.save(u, commitar)

    def atualizar(self, uuid: str, dados: dict, solicitante_eh_admin: bool, solicitante_uuid: str):
        u = self.buscar_por_uuid(uuid)
        eh_auto_edicao = (uuid == solicitante_uuid)

        # --- Camada 1: sanitização por papel ---------------------------
        if not solicitante_eh_admin:
            campos_bloqueados = [c for c in CAMPOS_RESTRITOS_A_ADMIN if c in dados]
            if campos_bloqueados:
                raise DadosInvalidosError(
                    f"Você não tem permissão para alterar: {', '.join(campos_bloqueados)}."
                )

        # --- Camada 2: admin não pode se autorrebaixar ------------------
        if eh_auto_edicao and "tipo_usuario" in dados and dados["tipo_usuario"] != u.tipo_usuario:
            raise DadosInvalidosError("Você não pode alterar seu próprio tipo de usuário.")

        # --- Camada 3: troca de tipo exige os novos atributos completos -
        atributos_atuais_u = atributos_atuais(u)
        novo_tipo = dados.get("tipo_usuario", u.tipo_usuario)
        tipo_mudou = novo_tipo != u.tipo_usuario

        if tipo_mudou:
            if novo_tipo == "medico" and not (dados.get("numero-crm") and dados.get("uf-crm")):
                raise DadosInvalidosError("Troca para médico exige 'numero-crm' e 'uf-crm'.")
            if novo_tipo == "enfermeiro" and not (
                dados.get("numero-coren") and dados.get("uf-coren") and dados.get("especialidade")
            ):
                raise DadosInvalidosError(
                    "Troca para enfermeiro exige 'numero-coren', 'uf-coren' e 'especialidade'."
                )

        try:
            schema_parcial = AtualizacaoUsuarioSchema(**dados)
        except Exception as e:
            raise DadosInvalidosError(f"Erro de validação: {e}") from e

        campos_enviados = schema_parcial.model_dump(exclude_unset=True, exclude_none=True)
        if not campos_enviados:
            raise DadosInvalidosError("Nenhum campo para atualizar foi enviado.")

        cpf_novo = campos_enviados.get("cpf")
        email_novo = campos_enviados.get("email")
        login_novo = campos_enviados.get("user_login")

        cpf_hash_novo = hmac_sha256(cpf_novo) if cpf_novo else None
        cpf_mudou = bool(cpf_hash_novo) and cpf_hash_novo != u.cpf_hash

        self._checar_duplicidade(
            cpf_hash=cpf_hash_novo if cpf_mudou else None,
            email=email_novo if email_novo and email_novo != u.email else None,
            login=login_novo if login_novo and login_novo != u.user_login else None,
            ignorar_uuid=uuid,
        )

        cpf_para_validar = campos_enviados.get("cpf") or aes_decrypt(u.cpf)

        dados_mesclados = {
            "nome_completo": u.nome_completo,
            "cpf": cpf_para_validar,
            "email": u.email,
            "user_login": u.user_login,
            "tipo_usuario": u.tipo_usuario,
            "telefone": u.telefone,
            "numero-crm": atributos_atuais_u.get("numero-crm"),
            "uf-crm": atributos_atuais_u.get("uf-crm"),
            "rqe": atributos_atuais_u.get("rqe"),
            "numero-coren": atributos_atuais_u.get("numero-coren"),
            "uf-coren": atributos_atuais_u.get("uf-coren"),
            "especialidade": atributos_atuais_u.get("especialidade"),
        }
        dados_mesclados.update(dados)

        try:
            schema_completo = CadastroUsuarioSchema(**dados_mesclados)
        except Exception as e:
            raise DadosInvalidosError(f"Erro de validação: {e}") from e

        for campo in CAMPOS_SIMPLES_ATUALIZAVEIS:
            if campo in campos_enviados:
                setattr(u, campo, getattr(schema_completo, campo))

        if "cpf" in campos_enviados:
            u.cpf = aes_encrypt(schema_completo.cpf)
            u.cpf_hash = hmac_sha256(schema_completo.cpf)

        if "senha" in campos_enviados:
            u.hash_senha = ph.hash(campos_enviados["senha"])

        if tipo_mudou or any(
            c in campos_enviados
            for c in ("numero_crm", "uf_crm", "rqe", "numero_coren", "uf_coren", "especialidade")
        ):
            u.tipo_usuario = schema_completo.tipo_usuario
            u.atributos_profissionais_json = monta_atributos_json(schema_completo)

        return self.repo.save(u)

    def desativar(self, uuid: str):
        u = self.buscar_por_uuid(uuid)
        u.status = "inativo"
        return self.repo.save(u)

    def ativar(self, uuid: str):
        u = self.buscar_por_uuid(uuid)
        u.status = "ativo"
        return self.repo.save(u)