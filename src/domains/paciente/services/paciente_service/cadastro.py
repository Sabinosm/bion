"""Cadastro de Paciente: cadastrar, cadastrar_nao_identificado e identificar.

Depende de `self.repo` e de LeituraMixin.buscar_por_uuid.
"""
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, hmac_sha256
from src.domains.paciente.schemas.schema_paciente import (
    erros_pydantic_por_campo, PacienteCriarSchema,
)
from src.domains.regiao.cep_service import CepService

from .helpers import _violou_cpf_unico


class CadastroMixin:
    """Cadastro: cadastrar, cadastrar_nao_identificado e identificar."""

    def _validar_criar(self, dados: dict, id_empresa: int) -> PacienteCriarSchema:
        """Valida o corpo de cadastro (Pydantic) e garante que o CPF ainda
        não existe NESTA empresa. Escopado por empresa: o mesmo CPF pode
        já existir como paciente de OUTRA empresa -- isso é normal (mesma
        pessoa atendida em clínicas diferentes) e não bloqueia o cadastro."""
        try:
            entrada = PacienteCriarSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        if self.repo.find_por_cpf_hash(hmac_sha256(entrada.cpf), id_empresa):
            raise ConflictoError("Já existe um paciente cadastrado com este CPF nesta empresa.")
        return entrada

    def _regiao_e_bairro(self, entrada: PacienteCriarSchema):
        """id_regiao_geografica: sempre derivado do cep, nunca aceito cru
        do payload. bairro: o do payload tem prioridade; só cai no
        resolvido via CEP se vier ausente. Sem cep, ambos ficam como
        vieram (região None). Se o cep vier mas a região não resolver, o
        cadastro inteiro falha. As duas chamadas ao CepService batem no
        mesmo cache em memória por CEP, então não repetem a requisição
        HTTP à BrasilAPI/ViaCEP."""
        id_regiao_geografica = None
        bairro = entrada.bairro
        if entrada.cep:
            cep_service = CepService()
            regiao = cep_service.regiao_por_cep(entrada.cep)
            if regiao is None:
                raise DadosInvalidosError(
                    "Não foi possível resolver a região geográfica a partir do CEP informado."
                )
            id_regiao_geografica = regiao.id_regiao_geografica
            if bairro is None:
                bairro = cep_service.buscar_bairro_por_cep(entrada.cep)
        return id_regiao_geografica, bairro

    @staticmethod
    def _montar_pessoal(id_paciente: int, id_empresa: int, e: PacienteCriarSchema):
        """Monta PacienteDadosPessoais com PII cifrada (AES) + cpf_hash
        (HMAC) para busca exata. Só instancia; não persiste.

        id_empresa: SEMPRE o de Paciente (paciente.id_empresa / empresa da
        sessão), nunca do payload -- é o que sustenta a UNIQUE composta
        (id_empresa, cpf_hash) no banco."""
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
        """Cadastra Paciente + PacienteDadosPessoais numa ÚNICA transação --
        antes eram dois commits separados, e uma falha no segundo deixava
        um Paciente órfão, sem dados pessoais. Tipo sanguíneo NÃO entra
        aqui: é dado clínico, registrado dentro de um Atendimento.

        Validação de formato em PacienteCriarSchema. Região derivada do
        cep e bairro com prioridade para o payload: ver _regiao_e_bairro.

        commit=False: deixa tudo pendente (flush) para o chamador (ex:
        ConsultaService.abrir, que cria a Consulta na mesma transação)."""
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
            # Corrida entre duas requisições com o mesmo CPF: a checagem de
            # _validar_criar passou nas duas, a UNIQUE composta barrou a 2ª.
            # Com commit=False a sessão fica inutilizável até o rollback, e
            # quem controla a transação (ex: ConsultaService.abrir) é quem o faz.
            if commit:
                self.repo.rollback()
            if _violou_cpf_unico(e):
                raise ConflictoError("Já existe um paciente cadastrado com este CPF nesta empresa.") from e
            raise
        except Exception:
            if commit:
                self.repo.rollback()
            raise

    def cadastrar_nao_identificado(self, sexo_biologico: str, id_usuario: int, id_empresa: int,
                                   commit: bool = True):
        """Emergência (SAMU, inconsciente): Paciente mínimo, SEM
        PacienteDadosPessoais, marcado nao_identificado=True. Não é o
        mesmo que anonimizado (LGPD): aquele já teve dados pessoais e os
        perdeu; este ainda não os teve. Quando a pessoa for identificada,
        use `identificar` -- completa este mesmo registro, sem duplicar."""
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
        """Completa um paciente de emergência com os dados de cadastro
        (mesmo corpo de `cadastrar`). Evita criar um 2º Paciente quando a
        pessoa é identificada depois -- o histórico de consulta,
        consentimento e atendimento já gravado fica no mesmo registro.

        data_primeiro_atendimento NÃO é sobrescrita: vale o dia em que a
        pessoa de fato chegou, não o que veio no corpo."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)
        # Guard de óbito: identificar é fluxo operacional/clínico de quem
        # está sendo atendido. (atualizar_pessoal e anonimizar ficam SEM
        # este guard de propósito: corrigir cadastro de falecido é legítimo.)
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
                raise ConflictoError("Já existe um paciente cadastrado com este CPF nesta empresa.") from e
            raise
        except Exception:
            if commit:
                self.repo.rollback()
            raise
        