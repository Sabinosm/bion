from datetime import datetime, timezone, date

from pydantic import ValidationError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt, hmac_sha256
from ..repositories import (
    PacienteRepository,
    ObservacaoTipoSanguineoRepository,
)
from src.schemas.schema_paciente import (
    PacienteAtualizarPessoalSchema, PacienteAtualizarClinicoSchema, _formatar_erros_pydantic, PacienteCriarSchema, 
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

    def __init__(self):
        self.repo = PacienteRepository()
        self.tipo_sanguineo_repo = ObservacaoTipoSanguineoRepository()

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


    def cadastrar(self, dados: dict, id_usuario_cadastro: int, id_empresa: int):
        """
        ALTERADO: validação movida para PacienteCriarSchema (Pydantic) --
        antes só checava presença dos 4 campos obrigatórios com uma lista
        manual, sem validar formato de nada (cpf sem dígito verificador,
        telefone/cep sem checagem real). Ver schema_paciente_create.py
        para o que cada campo aceita.
    
        id_regiao_geografica não é aceito como input direto: se 'cep'
        vier no payload, a região é RESOLVIDA a partir dele via
        CepService.regiao_por_cep -- decisão confirmada (região deve
        refletir o endereço real do paciente, não um valor arbitrário
        mandado pelo cliente). Se o cep vier mas a resolução falhar,
        o cadastro inteiro falha (DadosInvalidosError). Sem cep, não há
        fallback: id_regiao_geografica fica None.
    
        bairro é diferente: É aceito como input direto (ver
        PacienteCriarSchema) porque pode divergir do bairro resolvido
        pelo CEP (que é uma generalização/centróide, não o endereço
        exato). Prioridade: bairro do payload > bairro resolvido via
        CepService > None.
        """
        from src.models.pacientes import Paciente, PacienteDadosPessoais
    
        try:
            entrada = PacienteCriarSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))
    
        cpf_cifrado = aes_encrypt(entrada.cpf)
        cpf_hash = hmac_sha256(entrada.cpf)
        # Escopado por empresa: o mesmo CPF pode já existir como paciente
        # de OUTRA empresa -- isso é normal (mesma pessoa atendida em
        # clínicas diferentes) e não deve bloquear o cadastro aqui.
        if self.repo.find_por_cpf_hash(cpf_hash, id_empresa):
            raise ConflictoError("Já existe um paciente cadastrado com este CPF nesta empresa.")
    
        # id_regiao_geografica: sempre derivado do cep, nunca aceito cru
        # do payload -- ver docstring. bairro: payload tem prioridade;
        # só cai no resolvido via CEP se vier ausente.
        id_regiao_geografica = None
        bairro = entrada.bairro
        if entrada.cep:
            cep_service = CepService()
            # Duas chamadas públicas do CepService (regiao_por_cep +
            # buscar_endereco_por_cep) em vez de reimplementar a resolução
            # aqui -- ambas batem no mesmo cache em memória por CEP dentro
            # do CepService, então a segunda chamada não repete a
            # requisição HTTP à BrasilAPI/ViaCEP, só reaproveita o cache.
            regiao = cep_service.regiao_por_cep(entrada.cep)
            if regiao is None:
                raise DadosInvalidosError(
                    "Não foi possível resolver a região geográfica a partir do CEP informado."
                )
            id_regiao_geografica = regiao.id_regiao_geografica
    
            if bairro is None:
                bairro = cep_service.buscar_bairro_por_cep(entrada.cep)
    
        paciente = Paciente(
            sexo_biologico=entrada.sexo_biologico,
            bairro=bairro,
            data_nascimento=entrada.data_nascimento,
            id_regiao_geografica=id_regiao_geografica,
            data_primeiro_atendimento=entrada.data_primeiro_atendimento
            or datetime.now(timezone.utc).date(),
            cadastrado_por=id_usuario_cadastro,
            id_empresa=id_empresa,
        )
        self.repo.save(paciente)
    
        # Se o cadastro já veio com tipo_sanguineo (ex: paciente
        # transferido de outro sistema, já com exame feito), registra
        # como primeira observação.
        if entrada.tipo_sanguineo:
            paciente.registrar_tipo_sanguineo(entrada.tipo_sanguineo, registrado_por=id_usuario_cadastro)
    
        pessoal = PacienteDadosPessoais(
            id_paciente=paciente.id,
            nome_completo=aes_encrypt(entrada.nome_completo),
            cpf=cpf_cifrado,
            cpf_hash=cpf_hash,
            rg=entrada.rg,
            telefone=aes_encrypt(entrada.telefone) if entrada.telefone else None,
            email=aes_encrypt(entrada.email) if entrada.email else None,
            logradouro=aes_encrypt(entrada.logradouro) if entrada.logradouro else None,
            numero_residencia=entrada.numero_residencia,
            cep=aes_encrypt(entrada.cep) if entrada.cep else None,
            contato_emergencia_nome=entrada.contato_emergencia_nome,
            contato_emergencia_telefone=(
                aes_encrypt(entrada.contato_emergencia_telefone)
                if entrada.contato_emergencia_telefone else None
            ),
        )
    
        from src.models import db
        db.session.add(pessoal)
        db.session.commit()
    
        return paciente

    
    def count_pacientes_hoje(self, id_empresa):
        return self.repo.count_pacientes_hoje(id_empresa=id_empresa)

    def count_pacientes(self, id_empresa):
        return self.repo.count_pacientes(id_empresa=id_empresa)
    
    def atualizar_pessoal(self, uuid: str, dados: dict, id_empresa: int):
            """Corrigir cadastro (nome, telefone, endereço, etc) -- ação de
            gestão de dados, não decisão clínica. Médico, enfermeiro e
            admin podem chamar isso (ver controller); este método nunca
            escreve em campos clínicos, mesmo que o payload contenha uma
            chave 'status' por engano (schema nem aceita esse campo).
    
            ALTERADO: validação de formato movida para
            PacienteAtualizarPessoalSchema (Pydantic) -- antes qualquer
            string era aceita sem checagem para telefone/email/cep."""
            paciente = self.buscar_por_uuid(uuid, id_empresa)
            if not paciente.pessoal:
                raise DadosInvalidosError("Paciente está anonimizado; não há dados pessoais para atualizar.")
    
            try:
                entrada = PacienteAtualizarPessoalSchema(**dados)
            except ValidationError as e:
                raise DadosInvalidosError(_formatar_erros_pydantic(e))
    
            campos = entrada.campos_informados()
            campos_texto_cifrado = ("nome_completo", "telefone", "email", "logradouro", "cep",
                                     "contato_emergencia_telefone")
            for campo in campos_texto_cifrado:
                if campo in campos:
                    setattr(paciente.pessoal, campo, aes_encrypt(campos[campo]))
            for campo in ("rg", "numero_residencia", "contato_emergencia_nome"):
                if campo in campos:
                    setattr(paciente.pessoal, campo, campos[campo])
    
            return self.repo.save(paciente)
        
    def atualizar_clinico(self, uuid: str, dados: dict, id_empresa: int):
        """Status, falecido e data_obito são decisões clínicas.
        Reservado por padrão a médico/enfermeiro no controller; admin
        só entra aqui em caso excepcional, e essa chamada específica
        fica registrada (ver registrar_escrita_clinica_excepcional).

        ALTERADO: validação movida para PacienteAtualizarClinicoSchema
        -- status agora é Literal (antes um valor fora do Enum só
        falhava no commit()). O schema também aplica a regra
        confirmada: falecido=True força status="obito" automaticamente
        (via de mão única -- status="obito" sozinho não obriga
        falecido=True nem data_obito)."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)

        try:
            entrada = PacienteAtualizarClinicoSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(_formatar_erros_pydantic(e))

        campos = entrada.campos_informados()
        if "status" in campos:
            paciente.status = campos["status"]
        if "falecido" in campos:
            paciente.falecido = campos["falecido"]
        if "data_obito" in campos:
            paciente.data_obito = campos["data_obito"]

        return self.repo.save(paciente)

    def registrar_escrita_clinica_excepcional(self, uuid: str, id_usuario: int, acao: str):
        """Chamado pelo controller quando um admin (não
        médico/enfermeiro) grava algo clínico -- caso excepcional
        previsto (ex: médico responsável pediu apoio do admin), não um
        fluxo de rotina. Não logamos leitura nem escrita pessoal (ruído
        alto, sinal baixo); este é o único ponto de log, justamente
        porque é a única situação em que o papel de quem escreveu
        diverge do que se espera pra aquele tipo de dado."""
        from src.models.auditoria import RegistroAuditoria
        from src.models import db
        db.session.add(RegistroAuditoria(
            id_usuario=id_usuario,
            acao=acao,
            entidade="paciente",
            entidade_uuid=uuid,
        ))
        db.session.commit()

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

    def anonimizar(self, uuid: str, id_empresa: int):
        """Delega para paciente.anonimizar() do model (já corrigido lá
        para de fato desligar PacienteDadosPessoais), em vez de
        duplicar essa lógica aqui -- uma só fonte de verdade para o
        que "anonimizar" significa."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)
        if not paciente.pessoal:
            raise DadosInvalidosError("Paciente já está anonimizado.")

        cpf_plaintext = aes_decrypt(paciente.pessoal.cpf)
        paciente.anonimizar(cpf_plaintext)

        from src.models import db
        db.session.commit()
        return paciente

    def montar_prontuario_completo(self, uuid: str, id_empresa: int):
        """agrega o paciente + todos os domínios clínicos num
        único dict -- usado SÓ na tela de detalhe (nunca em listagem;
        cada domínio aqui é uma query própria, custo alto demais para
        repetir por paciente numa lista).

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
