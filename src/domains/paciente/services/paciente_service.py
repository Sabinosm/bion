from datetime import datetime, timezone, date

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt, hmac_sha256
from ..repositories import (
    PacienteRepository,
    ObservacaoTipoSanguineoRepository,
)

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

    #TODO : adicionar bairro utilizando do cep_service, no cadastro do paciente
    def cadastrar(self, dados: dict, id_usuario_cadastro: int, id_empresa: int):
        from src.models.pacientes import Paciente, PacienteDadosPessoais

        obrigatorios = ("sexo_biologico", "data_nascimento", "nome_completo", "cpf")
        faltando = [c for c in obrigatorios if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")

        cpf_cifrado = aes_encrypt(dados["cpf"])
        cpf_hash = hmac_sha256(dados["cpf"])
        # Escopado por empresa: o mesmo CPF pode já existir como paciente
        # de OUTRA empresa -- isso é normal (mesma pessoa atendida em
        # clínicas diferentes) e não deve bloquear o cadastro aqui.
        if self.repo.find_por_cpf_hash(cpf_hash, id_empresa):
            raise ConflictoError("Já existe um paciente cadastrado com este CPF nesta empresa.")

        paciente = Paciente(
            sexo_biologico=dados["sexo_biologico"],
            # tipo_sanguineo REMOVIDO do construtor -- ver abaixo
            data_nascimento=_parse_data(dados["data_nascimento"]),
            id_regiao_geografica=dados.get("id_regiao_geografica"),
            data_primeiro_atendimento=_parse_data(dados.get("data_primeiro_atendimento"))
            or datetime.now(timezone.utc).date(),
            cadastrado_por=id_usuario_cadastro,
            id_empresa=id_empresa,
        )
        self.repo.save(paciente)

        # Se o cadastro já veio com tipo_sanguineo (ex: paciente
        # transferido de outro sistema, já com exame feito), registra
        # como primeira observação.

        if dados.get("tipo_sanguineo"):
            paciente.registrar_tipo_sanguineo(dados["tipo_sanguineo"], registrado_por=id_usuario_cadastro)

        pessoal = PacienteDadosPessoais(
            id_paciente=paciente.id,
            nome_completo=aes_encrypt(dados["nome_completo"]),
            cpf=cpf_cifrado,
            cpf_hash=cpf_hash,
            rg=dados.get("rg"),
            telefone=aes_encrypt(dados.get("telefone")),
            email=aes_encrypt(dados.get("email")),
            logradouro=aes_encrypt(dados.get("logradouro")),
            numero_residencia=dados.get("numero_residencia"),
            cep=aes_encrypt(dados.get("cep")),
            contato_emergencia_nome=dados.get("contato_emergencia_nome"),
            contato_emergencia_telefone=aes_encrypt(dados.get("contato_emergencia_telefone")),
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
        chave 'status' por engano (é ignorada aqui)."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)
        if not paciente.pessoal:
            raise DadosInvalidosError("Paciente está anonimizado; não há dados pessoais para atualizar.")

        campos_texto_cifrado = ("nome_completo", "telefone", "email", "logradouro", "cep",
                                 "contato_emergencia_telefone")
        for campo in campos_texto_cifrado:
            if campo in dados:
                setattr(paciente.pessoal, campo, aes_encrypt(dados[campo]))
        for campo in ("rg", "numero_residencia", "contato_emergencia_nome"):
            if campo in dados:
                setattr(paciente.pessoal, campo, dados[campo])

        return self.repo.save(paciente)

    def atualizar_clinico(self, uuid: str, dados: dict, id_empresa: int):
        """Status, falecido e data_obito são decisões clínicas.
        Reservado por padrão a médico/enfermeiro no controller; admin
        só entra aqui em caso excepcional, e essa chamada específica
        fica registrada (ver registrar_escrita_clinica_excepcional)."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)

        if "status" in dados:
            paciente.status = dados["status"]
        if "falecido" in dados:
            paciente.falecido = bool(dados["falecido"])
        if "data_obito" in dados:
            paciente.data_obito = _parse_data(dados["data_obito"])

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
        """NOVO: agrega o paciente + todos os domínios clínicos num
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

        Import direto dos módulos (não via
        src.domains.paciente.services, o __init__.py agregador) --
        este arquivo já é um dos módulos importados por aquele
        __init__.py, então importar de volta o pacote inteiro criaria
        dependência circular. Import local (dentro do método, não no
        topo do arquivo) continua necessário para não carregar todos
        os services de domínio toda vez que PacienteService for
        instanciado, quando a maioria das chamadas nem usa o agregador.
        """
        from .alergia_service import AlergiaService
        from .doenca_cronica_service import DoencaCronicaService
        from .medicamento_em_uso_service import MedicamentoEmUsoService
        from .consentimento_service import ConsentimentoService

        paciente = self.buscar_por_uuid(uuid, id_empresa)

        alergia_svc = AlergiaService()
        doenca_svc = DoencaCronicaService()
        medicamento_svc = MedicamentoEmUsoService()
        consentimento_svc = ConsentimentoService()

        alergias = alergia_svc.listar_alergias(uuid, id_empresa)
        doencas = doenca_svc.listar_doencas(uuid, id_empresa)
        medicamentos = medicamento_svc.listar_medicamentos_em_uso(uuid, id_empresa)
        consentimento_ativo = consentimento_svc.repo.find_ativo_por_paciente(paciente.id) is not None

        # ALTERADO: alergias ordenadas por gravidade (grave primeiro),
        # não por ordem de cadastro -- uma alergia grave cadastrada há
        # anos não deveria aparecer depois de uma leve cadastrada ontem.
        ordem_gravidade = {"grave": 0, "moderada": 1, "leve": 2, None: 3}
        alergias_ordenadas = sorted(alergias, key=lambda a: ordem_gravidade.get(a.gravidade, 3))

        d = paciente.to_dict()
        d["resumo_clinico"] = self._montar_resumo_clinico(alergias, doencas, medicamentos)
        d["alergias"] = [a.to_dict() for a in alergias_ordenadas]
        d["doencas_cronicas"] = [doenca.to_dict() for doenca in doencas]
        d["medicamentos_em_uso"] = [m.to_dict() for m in medicamentos]
        d["consentimento_ativo"] = consentimento_ativo
        return d

    def _montar_resumo_clinico(self, alergias, doencas, medicamentos):
        """NOVO: bloco de alerta no TOPO do prontuário -- pensado para
        ser lido em segundos numa emergência, sem precisar percorrer
        cada array pra saber se há algo grave. Cada resumo é calculado
        aqui (não fica salvo em banco) para nunca divergir dos dados
        reais nas listas completas logo abaixo no mesmo JSON.
        """
        alergias_graves = [a.substancia for a in alergias if a.gravidade == "grave"]
        return {
            "alergias": {
                "total": len(alergias),
                "tem_grave": bool(alergias_graves),
                "resumo": [f"{a.substancia} ({a.gravidade or 'sem reação registrada'})" for a in alergias],
            },
            "doencas_cronicas": {
                "total": len(doencas),
                "ativas": sum(1 for d in doencas if d.status == "ativa"),
                "resumo": [d.descricao_cid10 for d in doencas if d.status == "ativa"],
            },
            "medicamentos_em_uso": {
                "total": len(medicamentos),
                "em_uso_continuo": sum(1 for m in medicamentos if m.status_uso == "ativo"),
                "resumo": [m.descricao for m in medicamentos if m.status_uso == "ativo"],
            },
        }