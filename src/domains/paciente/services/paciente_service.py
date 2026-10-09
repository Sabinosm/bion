from datetime import datetime, timezone, date

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt, hmac_sha256
from ..repositories import (
    PacienteRepository,
    ObservacaoTipoSanguineoRepository,
)
from src.domains.paciente.schemas.schema_paciente import (
    PacienteAtualizarPessoalSchema, PacienteAtualizarClinicoSchema, erros_pydantic_por_campo, PacienteCriarSchema,
)
from src.domains.regiao.cep_service import CepService

def _parse_data(valor):
    """Aceita date/datetime já convertidos ou string ISO 'YYYY-MM-DD' vinda do JSON."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise DadosInvalidosError(f"Data inválida: '{valor}'. Use o formato YYYY-MM-DD.")


_CONSTRAINT_CPF_EMPRESA = "uq_paciente_pessoal_empresa_cpf"


def _violou_cpf_unico(e: IntegrityError) -> bool:
    """True só quando o IntegrityError é a UNIQUE (id_empresa, cpf_hash).
    Qualquer outra violação (FK, enum, NOT NULL) NÃO pode ser traduzida
    para "CPF duplicado": esconderia o erro real. O nome da constraint
    aparece na mensagem do driver tanto no MySQL quanto no Postgres."""
    return _CONSTRAINT_CPF_EMPRESA in str(getattr(e, "orig", e))


class PacienteService:
    """Regras de negócio de Paciente.

    TRANSAÇÃO: este service NÃO toca em db.session. Todo commit, flush e
    rollback é delegado a PacienteRepository (ver `confirmar`, `save`,
    `rollback`). Os métodos de escrita aceitam `commit`:
      - commit=True  (padrão): a operação confirma sozinha.
      - commit=False: fica pendente (flush) para o chamador comitar junto
        com outras escritas -- ConsultaService.abrir (paciente + consulta
        + consentimento) e acao_sensivel (alteração + log) dependem disso.
    Com commit=False o rollback em caso de erro é responsabilidade de quem
    controla a transação; com commit=True o service desfaz sozinho.
    """

    def __init__(self):
        self.repo = PacienteRepository()
        self.tipo_sanguineo_repo = ObservacaoTipoSanguineoRepository()

    # ------------------------------------------------------------- leitura
    def buscar_por_uuid(self, uuid: str, id_empresa: int):
        p = self.repo.find_by_uuid(uuid, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid}")
        return p

    def listar(self, id_empresa: int):
        return self.repo.find_all(id_empresa)

    def listar_resumo(self, id_empresa: int, offset: int = 0, status: str = None,
                       sexo_biologico: str = None):
        """Listagem paginada já no formato enxuto (to_dict_few).
        Fica aqui e não no controller porque descriptografar nome/CPF
        é acesso a PII -- centralizado no service."""
        pacientes = self.repo.find_all_param(
            id_empresa=id_empresa, offset=offset, status=status,
            sexo_biologico=sexo_biologico,
        )
        resultado = []
        for p in pacientes:
            nome = aes_decrypt(p.pessoal.nome_completo) if p.pessoal else None
            cpf_inicio = None
            if p.pessoal and p.pessoal.cpf:
                cpf_inicio = aes_decrypt(p.pessoal.cpf)[:4]
            resultado.append(p.to_dict_few(nome_completo=nome, cpf_inicio=cpf_inicio))
        return resultado

    def buscar_valido(self, uuid: str, id_empresa: int):
        """Paciente da empresa que PODE receber atendimento: 404 se não
        existe (mesmo 404 de "outra empresa"), 409 com o motivo se existe
        mas não é válido. Para abrir consulta."""
        return self.exigir_valido(self.buscar_por_uuid(uuid, id_empresa))

    @staticmethod
    def exigir_valido(paciente):
        """Guard para quem já carregou o paciente (ex: Atendimento, que o
        obtém por atendimento -> consulta -> paciente). Critério único em
        Paciente.pode_receber_atendimento(); aqui só se escolhe a mensagem.
        Não vale para leitura de prontuário: histórico de falecido é
        consultável."""
        if paciente.pode_receber_atendimento():
            return paciente
        raise ConflictoError("Paciente com óbito registrado não pode receber atendimento.")

    def buscar_por_cpf(self, cpf_plaintext: str, id_empresa: int):
        p = self.repo.find_por_cpf_hash(hmac_sha256(cpf_plaintext), id_empresa)
        if not p:
            raise RecursoNaoEncontradoError("Paciente não encontrado para este CPF.")
        return p

    def count_pacientes_hoje(self, id_empresa):
        return self.repo.count_pacientes_hoje(id_empresa=id_empresa)

    def count_pacientes(self, id_empresa):
        return self.repo.count_pacientes(id_empresa=id_empresa)

    # ------------------------------------------------- helpers de cadastro
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

    # ------------------------------------------------------------ cadastro
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

    # ----------------------------------------------------------- atualização
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

    # ------------------------------------------------------------------ PII
    def dados_pessoais_descriptografados(self, paciente):
        """Usado pelo controller quando o usuário tem permissão de ver PII."""
        if not paciente.pessoal:
            return None
        p = paciente.pessoal
        return {
            "nome_completo": aes_decrypt(p.nome_completo),
            "cpf": aes_decrypt(p.cpf),
            "rg": p.rg,
            "telefone": aes_decrypt(p.telefone),
            "email": aes_decrypt(p.email),
            "logradouro": aes_decrypt(p.logradouro),
            "numero_residencia": p.numero_residencia,
            "cep": aes_decrypt(p.cep),
            "contato_emergencia_nome": p.contato_emergencia_nome,
            "contato_emergencia_telefone": aes_decrypt(p.contato_emergencia_telefone),
        }

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

    def montar_prontuario_completo(self, uuid: str, id_empresa: int):
        """Agrega o paciente + todos os domínios clínicos num único dict
        -- usado SÓ na tela de detalhe (nunca em listagem; cada domínio
        aqui é uma query própria, custo alto demais para repetir por
        paciente numa lista).

        CORRIGIDO: o parâmetro `commit` foi removido. Esta operação é só
        leitura, e o service o repassava a montar_prontuario_completo(),
        que não aceita esse argumento -- TypeError em toda chamada.

        Decisões confirmadas:
        - Consentimento fica FORA do agregado -- é sobre titularidade/
          LGPD, não é dado clínico. Só entra como um booleano
          (consentimento_ativo), não a lista de termos/histórico --
          quem quiser o histórico completo usa a rota própria do
          LgpdController.
        - Tipo sanguíneo: só o valor atual (via Paciente.tipo_sanguineo,
          já incluído em to_dict()). Histórico completo de observações
          fica de fora, exposto em endpoint separado.
        - resumo_clinico: bloco no topo do dict com contagens e alertas
          de alergia grave, doença crônica ativa e medicamento em uso
          contínuo -- pensado para leitura rápida (emergência), sem
          precisar percorrer os arrays completos logo abaixo.
        """
        from .montar_prontuario_service import montar_prontuario_completo
        return montar_prontuario_completo(uuid, id_empresa)