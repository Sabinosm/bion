"""cadastro.py

Cadastro de Paciente: cadastro completo, cadastro de emergência (paciente não
identificado) e a identificação posterior desse paciente.

O cadastro completo grava Paciente e PacienteDadosPessoais numa ÚNICA transação,
com a PII cifrada e o CPF em hash para busca exata. A região geográfica é sempre
derivada do CEP, nunca aceita do corpo; o bairro informado tem prioridade sobre o
resolvido pelo CEP. Tipo sanguíneo não entra no cadastro: é dado clínico,
registrado dentro de um Atendimento. O CPF é único por empresa (a mesma pessoa
pode existir em empresas diferentes). Depende de `self.repo` e de
LeituraMixin.buscar_por_uuid.
"""
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, hmac_sha256
from src.domains.paciente.schemas.schema_paciente import PacienteCriarSchema

from ..comum import validar_schema
from .helpers import _regiao_e_bairro_do_cep, _violou_cpf_unico

_MSG_CPF_DUPLICADO = "Já existe um paciente cadastrado com este CPF nesta empresa."


class CadastroMixin:
    """Cadastro: cadastrar, cadastrar_nao_identificado e identificar."""

    def _validar_criar(self, dados: dict, id_empresa: int) -> PacienteCriarSchema:
        """Valida o corpo de cadastro e garante que o CPF ainda não existe NESTA empresa. O mesmo
        CPF em OUTRA empresa é normal (mesma pessoa atendida em clínicas diferentes) e não bloqueia.

        Raises:
            DadosInvalidosError: corpo inválido (erros por campo).
            ConflictoError: CPF já cadastrado na empresa.
        """
        entrada = validar_schema(PacienteCriarSchema, dados)
        if self.repo.find_por_cpf_hash(hmac_sha256(entrada.cpf), id_empresa):
            raise ConflictoError(_MSG_CPF_DUPLICADO)
        return entrada

    @staticmethod
    def _regiao_e_bairro(entrada: PacienteCriarSchema):
        """Devolve (id_regiao_geografica, bairro) do corpo de cadastro (ver _regiao_e_bairro_do_cep).

        Raises:
            DadosInvalidosError: CEP informado cuja região não foi resolvida.
        """
        return _regiao_e_bairro_do_cep(entrada.cep, entrada.bairro)

    @staticmethod
    def _montar_pessoal(id_paciente: int, id_empresa: int, e: PacienteCriarSchema):
        """Monta PacienteDadosPessoais com a PII cifrada (AES) e o cpf_hash (HMAC) para busca
        exata. Só instancia; não persiste. `id_empresa` é SEMPRE o do Paciente (nunca do corpo): é
        ele que sustenta a UNIQUE composta (id_empresa, cpf_hash) no banco."""
        from src.models.pacientes import PacienteDadosPessoais
        return PacienteDadosPessoais(
            id_paciente=id_paciente,
            id_empresa=id_empresa,
            nome_completo=aes_encrypt(e.nome_completo),
            cpf=aes_encrypt(e.cpf),
            cpf_hash=hmac_sha256(e.cpf),
            rg=e.rg,
            telefone=aes_encrypt(e.telefone) if e.telefone else None,
            email=aes_encrypt(e.email) if e.email else None,
            logradouro=aes_encrypt(e.logradouro) if e.logradouro else None,
            numero_residencia=e.numero_residencia,
            cep=aes_encrypt(e.cep) if e.cep else None,
            contato_emergencia_nome=e.contato_emergencia_nome,
            contato_emergencia_telefone=(
                aes_encrypt(e.contato_emergencia_telefone)
                if e.contato_emergencia_telefone else None
            ),
        )

    def cadastrar(self, dados: dict, id_usuario_cadastro: int, id_empresa: int, commit: bool = True):
        """Cadastra Paciente + PacienteDadosPessoais numa ÚNICA transação (uma falha no segundo
        não deixa Paciente órfão, sem dados pessoais).

        commit=False deixa tudo pendente (flush) para o chamador (ex.: ConsultaService.abrir, que
        cria a Consulta na mesma transação).

        Raises:
            DadosInvalidosError: corpo inválido ou CEP sem região.
            ConflictoError: CPF já cadastrado na empresa (inclusive em corrida entre duas
                requisições, barrada pela UNIQUE composta).
        """
        from src.models.pacientes import Paciente

        entrada = self._validar_criar(dados, id_empresa)
        id_regiao, bairro = self._regiao_e_bairro(entrada)

        try:
            paciente = Paciente(
                sexo_biologico=entrada.sexo_biologico,
                bairro=bairro,
                data_nascimento=entrada.data_nascimento,
                id_regiao_geografica=id_regiao,
                data_primeiro_atendimento=entrada.data_primeiro_atendimento
                or datetime.now(timezone.utc).date(),
                cadastrado_por=id_usuario_cadastro,
                id_empresa=id_empresa,
            )
            self.repo.save(paciente, commit=False)  # flush: precisa do id

            pessoal = self._montar_pessoal(paciente.id, id_empresa, entrada)
            paciente.pessoal = pessoal
            self.repo.save(pessoal, commit=commit)  # único commit do cadastro
            return paciente
        except IntegrityError as e:
            # Corrida de duas requisições com o mesmo CPF: a checagem prévia passou nas duas e a
            # UNIQUE composta barrou a 2ª. Com commit=False a sessão fica inutilizável até o
            # rollback, que é de quem controla a transação (ex.: ConsultaService.abrir).
            if commit:
                self.repo.rollback()
            if _violou_cpf_unico(e):
                raise ConflictoError(_MSG_CPF_DUPLICADO) from e
            raise
        except Exception:
            if commit:
                self.repo.rollback()
            raise

    def cadastrar_nao_identificado(self, sexo_biologico: str, id_usuario: int, id_empresa: int,
                                   commit: bool = True):
        """Emergência (SAMU, inconsciente): Paciente mínimo, SEM PacienteDadosPessoais, marcado
        nao_identificado=True. Não é o mesmo que anonimizado (LGPD): aquele já teve dados pessoais
        e os perdeu; este ainda não os teve. Quando a pessoa for identificada, use `identificar`,
        que completa este mesmo registro sem duplicar.

        Raises:
            DadosInvalidosError: sexo_biologico fora de M, F ou I.
        """
        from src.models.pacientes import Paciente

        if sexo_biologico not in ("M", "F", "I"):
            raise DadosInvalidosError("sexo_biologico inválido. Use M, F ou I.")

        try:
            paciente = Paciente(
                sexo_biologico=sexo_biologico,
                nao_identificado=True,
                data_primeiro_atendimento=datetime.now(timezone.utc).date(),
                cadastrado_por=id_usuario,
                id_empresa=id_empresa,
            )
            return self.repo.save(paciente, commit=commit)
        except Exception:
            if commit:
                self.repo.rollback()
            raise

    def identificar(self, uuid: str, dados: dict, id_usuario: int, id_empresa: int, commit: bool = True):
        """Completa um paciente de emergência com os dados de cadastro (mesmo corpo de `cadastrar`).
        Evita um 2º Paciente quando a pessoa é identificada depois: o histórico de consulta,
        consentimento e atendimento já gravado fica no mesmo registro. A data do primeiro
        atendimento NÃO é sobrescrita (vale o dia em que a pessoa de fato chegou).

        Identificar é fluxo clínico de quem está sendo atendido, então paciente falecido é
        recusado aqui (já atualizar_pessoal e anonimizar não têm esse guard de propósito: corrigir
        cadastro de falecido é legítimo).

        Raises:
            RecursoNaoEncontradoError: paciente inexistente na empresa.
            ConflictoError: paciente falecido, já identificado, ou CPF já cadastrado na empresa.
            DadosInvalidosError: corpo inválido ou CEP sem região.
        """
        paciente = self.buscar_por_uuid(uuid, id_empresa)
        if paciente.esta_falecido():
            raise ConflictoError(
                "Paciente com óbito registrado não pode ser identificado por este fluxo."
            )
        if not paciente.nao_identificado:
            raise ConflictoError("Paciente já está identificado.")

        entrada = self._validar_criar(dados, id_empresa)
        id_regiao, bairro = self._regiao_e_bairro(entrada)

        try:
            paciente.sexo_biologico = entrada.sexo_biologico
            paciente.bairro = bairro
            paciente.data_nascimento = entrada.data_nascimento
            paciente.id_regiao_geografica = id_regiao
            paciente.nao_identificado = False

            pessoal = self._montar_pessoal(paciente.id, paciente.id_empresa, entrada)
            paciente.pessoal = pessoal
            self.repo.save(pessoal, commit=False)
            return self.repo.save(paciente, commit=commit)
        except IntegrityError as e:
            if commit:
                self.repo.rollback()
            if _violou_cpf_unico(e):
                raise ConflictoError(_MSG_CPF_DUPLICADO) from e
            raise
        except Exception:
            if commit:
                self.repo.rollback()
            raise
