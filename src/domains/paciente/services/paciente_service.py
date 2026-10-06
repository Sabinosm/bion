from datetime import datetime, timezone, date

from pydantic import ValidationError

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
    def _montar_pessoal(id_paciente: int, e: PacienteCriarSchema):
        """Monta PacienteDadosPessoais com PII cifrada (AES) + cpf_hash
        (HMAC) para busca exata. Só instancia; não persiste."""
        from src.models.pacientes import PacienteDadosPessoais
        return PacienteDadosPessoais(
            id_paciente=id_paciente,
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
        """Cadastra Paciente + PacienteDadosPessoais (+ tipo sanguíneo
        inicial, se vier) numa ÚNICA transação -- antes eram dois commits
        separados, e uma falha no segundo deixava um Paciente órfão, sem
        dados pessoais.

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

            # Cadastro já com tipo_sanguineo (ex: paciente transferido de
            # outro sistema, com exame feito) entra como 1ª observação.
            if entrada.tipo_sanguineo:
                paciente.registrar_tipo_sanguineo(
                    entrada.tipo_sanguineo, registrado_por=id_usuario_cadastro
                )

            pessoal = self._montar_pessoal(paciente.id, entrada)
            paciente.pessoal = pessoal
            self.repo.save(pessoal, commit=commit)  # único commit do cadastro
            return paciente
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

            if entrada.tipo_sanguineo:
                paciente.registrar_tipo_sanguineo(entrada.tipo_sanguineo, registrado_por=id_usuario)

            pessoal = self._montar_pessoal(paciente.id, entrada)
            paciente.pessoal = pessoal
            self.repo.save(pessoal, commit=False)
            return self.repo.save(paciente, commit=commit)
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

    def atualizar_clinico(self, uuid: str, dados: dict, id_empresa: int, commit: bool = True):
        """Status, falecido e data_obito são decisões clínicas.
        Reservado por padrão a médico/enfermeiro no controller; admin
        só entra aqui em caso excepcional, e essa chamada específica
        fica registrada (ver registrar_escrita_clinica_excepcional).

        Validação em PacienteAtualizarClinicoSchema -- status é Literal.
        O schema também aplica a regra confirmada: falecido=True força
        status="obito" (mão única -- status="obito" sozinho não obriga
        falecido=True nem data_obito)."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)

        try:
            entrada = PacienteAtualizarClinicoSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        campos = entrada.campos_informados()
        if "status" in campos:
            paciente.status = campos["status"]
        if "falecido" in campos:
            paciente.falecido = campos["falecido"]
        if "data_obito" in campos:
            paciente.data_obito = campos["data_obito"]

        return self._salvar(paciente, commit)

    def _salvar(self, paciente, commit: bool):
        """save com rollback automático quando o service é quem comita."""
        try:
            return self.repo.save(paciente, commit=commit)
        except Exception:
            if commit:
                self.repo.rollback()
            raise

    def registrar_escrita_clinica_excepcional(self, uuid: str, id_usuario: int, acao: str,
                                              commit: bool = True):
        """Chamado pelo controller quando um admin (não
        médico/enfermeiro) grava algo clínico -- caso excepcional
        previsto (ex: médico responsável pediu apoio do admin), não um
        fluxo de rotina. Não logamos leitura nem escrita pessoal (ruído
        alto, sinal baixo); este é o único ponto de log, justamente
        porque é a única situação em que o papel de quem escreveu
        diverge do que se espera pra aquele tipo de dado."""
        self.repo.registrar_auditoria(id_usuario, acao, uuid, commit=commit)

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