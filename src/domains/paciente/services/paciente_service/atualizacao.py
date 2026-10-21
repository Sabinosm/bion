"""Alteração de Paciente já cadastrado: dados pessoais, status clínico, óbito,
anonimização e os helpers de save (rollback / auditoria atômica).

Depende de `self.repo` e de LeituraMixin.buscar_por_uuid.
"""
from datetime import datetime, timezone

from pydantic import ValidationError

from src.core.exceptions import DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt
from src.domains.paciente.schemas.schema_paciente import (
    PacienteAtualizarPessoalSchema, PacienteAtualizarClinicoSchema, erros_pydantic_por_campo,
)

from .helpers import _parse_data


class AtualizacaoMixin:
    """Atualização: pessoal, clínico, óbito, anonimização e persistência."""

    def atualizar_pessoal(self, uuid: str, dados: dict, id_empresa: int, commit: bool = True):
        """Corrigir cadastro (nome, telefone, endereço, etc) -- ação de
        gestão de dados, não decisão clínica. Médico, enfermeiro e
        admin podem chamar isso (ver controller); este método nunca
        escreve em campos clínicos, mesmo que o payload contenha uma
        chave 'status' por engano (schema nem aceita esse campo).

        Validação de formato em PacienteAtualizarPessoalSchema.

        CORRIGIDO: o `except Exception: raise` vinha ANTES de
        `except ValidationError`, então o segundo nunca executava e todo
        erro de validação subia como 500. Agora ValidationError vira
        DadosInvalidosError (400)."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)
        if not paciente.pessoal:
            if paciente.nao_identificado:
                raise DadosInvalidosError(
                    "Paciente não identificado: use /identificar para informar os dados pessoais."
                )
            raise DadosInvalidosError("Paciente está anonimizado; não há dados pessoais para atualizar.")

        try:
            entrada = PacienteAtualizarPessoalSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        campos = entrada.campos_informados()
        campos_texto_cifrado = ("nome_completo", "telefone", "email", "logradouro", "cep",
                                "contato_emergencia_telefone")
        for campo in campos_texto_cifrado:
            if campo in campos:
                setattr(paciente.pessoal, campo, aes_encrypt(campos[campo]))
        for campo in ("rg", "numero_residencia", "contato_emergencia_nome"):
            if campo in campos:
                setattr(paciente.pessoal, campo, campos[campo])

        return self._salvar(paciente, commit)

    def atualizar_clinico(self, uuid: str, dados: dict, id_empresa: int, commit: bool = True,
                          auditar_excecao_por: int = None):
        """Altera apenas `status`, entre "ativo" e "inativo".

        Óbito NÃO passa por aqui: status="obito", falecido e data_obito
        só mudam via marcar_obito / reverter_obito, que mantêm os três
        campos sempre sincronizados. O schema rejeita (422) falecido,
        data_obito e status="obito" neste payload.

        Reservado por padrão a médico/enfermeiro no controller; admin
        só entra aqui em caso excepcional, e essa chamada específica
        fica registrada.

        auditar_excecao_por: id do usuário admin que está gravando como
        exceção (None para médico/enfermeiro). Quando informado, a
        alteração e a linha de auditoria são gravadas na MESMA
        transação: ou entram as duas, ou nenhuma."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)

        try:
            entrada = PacienteAtualizarClinicoSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        if paciente.esta_falecido():
            raise ConflictoError(
                "Paciente com óbito registrado: use reverter_obito antes de alterar o status."
            )

        campos = entrada.campos_informados()
        if "status" in campos:
            paciente.status = campos["status"]

        return self._salvar_com_auditoria(paciente, commit, auditar_excecao_por, "atualizar_clinico")

    def _tem_consulta_aberta(self, paciente) -> bool:
        """True se o paciente tem Consulta aberta (não encerrada) na
        empresa dele. O critério vive em PacienteRepository.tem_consulta_aberta."""
        return self.repo.tem_consulta_aberta(paciente.id, paciente.id_empresa)

    def marcar_obito(self, uuid: str, data_obito, id_empresa: int, commit: bool = True,
                     auditar_excecao_por: int = None):
        """Registra o óbito mantendo status, falecido e data_obito
        sincronizados -- é a única via de entrada para esses três campos.

        Regras: data_obito obrigatória, não futura e não anterior ao
        nascimento; o paciente não pode já estar falecido nem ter
        consulta aberta (a consulta deve ser encerrada antes).

        auditar_excecao_por: id do admin gravando como exceção (None para
        médico/enfermeiro); escrita e auditoria na mesma transação."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)
        if paciente.esta_falecido():
            raise ConflictoError("Paciente já está com óbito registrado.")

        data = _parse_data(data_obito)
        if data is None:
            raise DadosInvalidosError("data_obito é obrigatória.")
        if data > datetime.now(timezone.utc).date():
            raise DadosInvalidosError("data_obito não pode ser uma data futura.")
        if paciente.data_nascimento and data < paciente.data_nascimento:
            raise DadosInvalidosError("data_obito não pode ser anterior à data de nascimento.")

        if self._tem_consulta_aberta(paciente):
            raise ConflictoError(
                "Paciente tem consulta aberta; encerre-a antes de registrar o óbito."
            )

        paciente.status = "obito"
        paciente.falecido = True
        paciente.data_obito = data
        return self._salvar_com_auditoria(paciente, commit, auditar_excecao_por, "marcar_obito")

    def reverter_obito(self, uuid: str, id_empresa: int, status_destino: str = "ativo",
                       commit: bool = True):
        """Desfaz um óbito marcado por engano. O status anterior não é
        guardado (foi sobrescrito por "obito"), por isso o destino é
        informado: "ativo" (padrão) ou "inativo". Limpa falecido e
        data_obito. No controller é acao_sensivel (step-up + justificativa
        + log atômico), por isso aceita commit=False."""
        if status_destino not in ("ativo", "inativo"):
            raise DadosInvalidosError("status_destino deve ser 'ativo' ou 'inativo'.")

        paciente = self.buscar_por_uuid(uuid, id_empresa)
        if not paciente.esta_falecido():
            raise ConflictoError("Paciente não está com óbito registrado.")

        paciente.status = status_destino
        paciente.falecido = False
        paciente.data_obito = None
        return self._salvar(paciente, commit)

    def anonimizar(self, uuid: str, id_empresa: int, commit: bool = True):
        """Delega para paciente.anonimizar() do model (já corrigido lá
        para de fato desligar PacienteDadosPessoais), em vez de
        duplicar essa lógica aqui -- uma só fonte de verdade para o
        que "anonimizar" significa.

        `commit`: o controller usa commit=False dentro de acao_sensivel,
        para a anonimização (irreversível) ser persistida JUNTO com o log
        de auditoria, no commit único do decorator. Com commit=True ela
        comitaria antes do log e, se o log falhasse, o paciente ficaria
        anonimizado sem rastro de quem fez ou quando."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)
        if not paciente.pessoal:
            if paciente.nao_identificado:
                raise DadosInvalidosError("Paciente não identificado: não há dados pessoais a anonimizar.")
            raise DadosInvalidosError("Paciente já está anonimizado.")

        cpf_plaintext = aes_decrypt(paciente.pessoal.cpf)
        paciente.anonimizar(cpf_plaintext)
        return self._salvar(paciente, commit)

    def _salvar(self, paciente, commit: bool):
        """save com rollback automático quando o service é quem comita."""
        try:
            return self.repo.save(paciente, commit=commit)
        except Exception:
            if commit:
                self.repo.rollback()
            raise

    def _salvar_com_auditoria(self, paciente, commit: bool, id_usuario_excecao, acao: str):
        """Grava o paciente e, se id_usuario_excecao vier, a linha de
        auditoria da escrita excepcional de admin, tudo na mesma
        transação: flush das duas e UM confirmar no fim. Com commit=False
        o chamador (ex: acao_sensivel) continua dono do commit."""
        try:
            self.repo.save(paciente, commit=False)
            if id_usuario_excecao is not None:
                self.repo.registrar_auditoria(id_usuario_excecao, acao, paciente.uuid, commit=False)
            self.repo.confirmar(commit)
            return paciente
        except Exception:
            if commit:
                self.repo.rollback()
            raise
