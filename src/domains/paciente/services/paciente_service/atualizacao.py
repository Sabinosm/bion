"""atualizacao.py

Alteração de Paciente já cadastrado: dados pessoais, status clínico (ativo ou
inativo), óbito (marcar e reverter) e anonimização, mais os helpers de
persistência (rollback automático e escrita com auditoria atômica).

Três eixos separados: corrigir cadastro é gestão de dados (nunca escreve campo
clínico); o status só alterna entre ativo e inativo; e o óbito só muda por
marcar/reverter, que mantêm status, falecido e data de óbito sempre sincronizados.
A escrita excepcional de admin no eixo clínico grava a alteração e a linha de
auditoria na MESMA transação. Depende de `self.repo` e de
LeituraMixin.buscar_por_uuid.
"""
from datetime import datetime, timezone

from src.core.exceptions import DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt
from src.domains.paciente.schemas.schema_paciente import (
    PacienteAtualizarPessoalSchema, PacienteAtualizarClinicoSchema,
)

from ..comum import validar_schema
from .helpers import _parse_data, _regiao_e_bairro_do_cep

_CAMPOS_PESSOAIS_CIFRADOS = ("nome_completo", "telefone", "email", "logradouro", "cep",
                             "contato_emergencia_telefone")
_CAMPOS_PESSOAIS_ABERTOS = ("rg", "numero_residencia", "contato_emergencia_nome")


class AtualizacaoMixin:
    """Atualização: pessoal, clínico, óbito, anonimização e persistência."""

    def atualizar_pessoal(self, uuid: str, dados: dict, id_empresa: int, commit: bool = True):
        """Corrige o cadastro (nome, telefone, endereço...), só os campos enviados. Ação de gestão de
        dados, não decisão clínica: nunca escreve campos clínicos (o schema nem aceita `status`).
        Um campo opcional enviado como `null` é limpo.

        Trocar o CEP **recalcula** a região geográfica e o bairro do paciente (a região é sempre
        derivada do CEP). O bairro só é trocado se o CEP novo o resolver; se não resolver, o anterior
        fica. Se o CEP novo não resolve a região, a atualização inteira falha (422), como no cadastro.

        Raises:
            RecursoNaoEncontradoError: paciente inexistente na empresa.
            DadosInvalidosError: paciente sem dados pessoais (não identificado ou anonimizado),
                corpo inválido (erros por campo) ou CEP novo sem região resolvida.
        """
        paciente = self.buscar_por_uuid(uuid, id_empresa)
        if not paciente.pessoal:
            if paciente.nao_identificado:
                raise DadosInvalidosError(
                    "Paciente não identificado: use /identificar para informar os dados pessoais."
                )
            raise DadosInvalidosError("Paciente está anonimizado; não há dados pessoais para atualizar.")

        entrada = validar_schema(PacienteAtualizarPessoalSchema, dados)
        campos = entrada.campos_informados()

        # Resolve antes de aplicar qualquer campo: se o CEP novo não resolve, nada é alterado.
        if campos.get("cep"):
            id_regiao, bairro = _regiao_e_bairro_do_cep(campos["cep"])
            paciente.id_regiao_geografica = id_regiao
            if bairro is not None:
                paciente.bairro = bairro

        for campo in _CAMPOS_PESSOAIS_CIFRADOS:
            if campo in campos:
                valor = campos[campo]
                setattr(paciente.pessoal, campo, None if valor is None else aes_encrypt(valor))
        for campo in _CAMPOS_PESSOAIS_ABERTOS:
            if campo in campos:
                setattr(paciente.pessoal, campo, campos[campo])

        return self._salvar(paciente, commit)

    def atualizar_clinico(self, uuid: str, dados: dict, id_empresa: int, commit: bool = True,
                          auditar_excecao_por: int = None):
        """Altera apenas `status`, entre "ativo" e "inativo".

        Óbito NÃO passa por aqui: status="obito", falecido e data_obito só mudam por marcar_obito e
        reverter_obito. O schema rejeita (422) falecido, data_obito e status="obito" neste corpo.

        `auditar_excecao_por`: id do admin gravando como exceção (None para médico/enfermeiro).
        Quando informado, a alteração e a linha de auditoria são gravadas na MESMA transação.

        Raises:
            DadosInvalidosError: corpo inválido.
            ConflictoError: paciente com óbito registrado.
        """
        paciente = self.buscar_por_uuid(uuid, id_empresa)
        entrada = validar_schema(PacienteAtualizarClinicoSchema, dados)

        if paciente.esta_falecido():
            raise ConflictoError(
                "Paciente com óbito registrado: use reverter_obito antes de alterar o status."
            )

        campos = entrada.campos_informados()
        if "status" in campos:
            paciente.status = campos["status"]

        return self._salvar_com_auditoria(paciente, commit, auditar_excecao_por, "atualizar_clinico")

    def _tem_consulta_aberta(self, paciente) -> bool:
        """True se o paciente tem Consulta aberta (não encerrada) na empresa dele. O critério vive
        em PacienteRepository.tem_consulta_aberta."""
        return self.repo.tem_consulta_aberta(paciente.id, paciente.id_empresa)

    def marcar_obito(self, uuid: str, data_obito, id_empresa: int, commit: bool = True,
                     auditar_excecao_por: int = None):
        """Registra o óbito mantendo status, falecido e data_obito sincronizados (é a única via de
        entrada para esses três campos).

        Regras: data_obito obrigatória, não futura e não anterior ao nascimento; o paciente não
        pode já estar falecido nem ter consulta aberta (encerre-a antes).

        Raises:
            ConflictoError: já falecido, ou com consulta aberta.
            DadosInvalidosError: data ausente, futura, anterior ao nascimento ou mal formatada.
        """
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
        """Desfaz um óbito marcado por engano. O status anterior não é guardado (foi sobrescrito por
        "obito"), então o destino é informado: "ativo" (padrão) ou "inativo". Limpa falecido e
        data_obito. No controller é ação sensível (step-up, justificativa e log atômico), por isso
        aceita commit=False.

        Raises:
            DadosInvalidosError: status_destino fora de ativo/inativo.
            ConflictoError: paciente não está com óbito registrado.
        """
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
        """Anonimização (LGPD), irreversível: delega para Paciente.anonimizar() do model, que é a
        única fonte de verdade do que "anonimizar" significa (desliga PacienteDadosPessoais).

        O controller usa commit=False dentro de uma ação sensível, para a anonimização ser
        persistida JUNTO com o log de auditoria, no commit único do decorator. Com commit=True ela
        comitaria antes do log e, se o log falhasse, o paciente ficaria anonimizado sem rastro.

        Raises:
            DadosInvalidosError: paciente não identificado ou já anonimizado (sem dados pessoais).
        """
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
        """Grava o paciente e, se `id_usuario_excecao` vier, a linha de auditoria da escrita
        excepcional de admin, tudo na mesma transação: flush das duas e UM confirmar no fim. Com
        commit=False o chamador (ex.: ação sensível) continua dono do commit."""
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
