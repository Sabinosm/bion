from datetime import datetime, timezone, date

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt, hmac_sha256
from ..repositories import (
    PacienteRepository, AlergiaRepository, ReacaoAlergiaRepository,
    DoencaCronicaRepository, MedicamentoEmUsoRepository, ConsentimentoRepository,
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

    def buscar_por_uuid(self, uuid: str):
        p = self.repo.find_by_uuid(uuid)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid}")
        return p

    def listar(self):
        return self.repo.find_all()

    def buscar_por_cpf(self, cpf_plaintext: str):
        p = self.repo.find_por_cpf_hash(hmac_sha256(cpf_plaintext))
        if not p:
            raise RecursoNaoEncontradoError("Paciente não encontrado para este CPF.")
        return p
    
    #TODO : adicionar bairro utilizando do cep_service, no cadastro do paciente
    def cadastrar(self, dados: dict, id_usuario_cadastro: int):
        from src.models.pacientes import Paciente, PacienteDadosPessoais

        obrigatorios = ("sexo_biologico", "data_nascimento", "nome_completo", "cpf")
        faltando = [c for c in obrigatorios if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")

        cpf_cifrado = aes_encrypt(dados["cpf"])
        cpf_hash = hmac_sha256(dados["cpf"])
        if self.repo.find_por_cpf_hash(cpf_hash):
            raise ConflictoError("Já existe um paciente cadastrado com este CPF.")

        paciente = Paciente(
            sexo_biologico=dados["sexo_biologico"],
            # tipo_sanguineo REMOVIDO do construtor -- ver abaixo
            data_nascimento=_parse_data(dados["data_nascimento"]),
            id_regiao_geografica=dados.get("id_regiao_geografica"),
            data_primeiro_atendimento=_parse_data(dados.get("data_primeiro_atendimento"))
            or datetime.now(timezone.utc).date(),
            cadastrado_por=id_usuario_cadastro,
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
    
    def count_pacientes(self,id_empresa):
        return self.repo.count_pacientes(id_empresa=id_empresa)
    

    def atualizar(self, uuid: str, dados: dict):
        """ALTERADO: tipo_sanguineo SAIU daqui -- ver
        registrar_tipo_sanguineo() e corrigir_tipo_sanguineo() abaixo,
        que são os pontos de entrada corretos agora (a rota decide
        qual chamar, conforme a intenção: novo exame vs correção)."""
        paciente = self.buscar_por_uuid(uuid)
        if "status" in dados:
            paciente.status = dados["status"]

        if paciente.pessoal:
            campos_texto_cifrado = ("nome_completo", "telefone", "email", "logradouro", "cep",
                                     "contato_emergencia_telefone")
            for campo in campos_texto_cifrado:
                if campo in dados:
                    setattr(paciente.pessoal, campo, aes_encrypt(dados[campo]))
            for campo in ("rg", "numero_residencia", "contato_emergencia_nome"):
                if campo in dados:
                    setattr(paciente.pessoal, campo, dados[campo])

        return self.repo.save(paciente)

    def registrar_tipo_sanguineo(self, uuid_paciente: str, valor: str, id_usuario: int):
        """NOVO exame/resultado -- cria uma observação adicional,
        preserva histórico. Este é o caminho normal de uso clínico."""
        paciente = self.buscar_por_uuid(uuid_paciente)
        paciente.registrar_tipo_sanguineo(valor, registrado_por=id_usuario)
        return self.repo.save(paciente)

    def corrigir_tipo_sanguineo(self, uuid_observacao: str, novo_valor: str):
        """CORREÇÃO de um registro específico já existente (erro de
        digitação) -- não cria histórico novo, edita o valor no lugar.
        Requer o uuid da observação específica, não do paciente."""
        obs = self.tipo_sanguineo_repo.corrigir(uuid_observacao, novo_valor)
        if not obs:
            raise RecursoNaoEncontradoError(f"Observação de tipo sanguíneo não encontrada: {uuid_observacao}")
        return obs

    def remover_tipo_sanguineo(self, uuid_observacao: str):
        """Remove um registro de observação por engano (ex: paciente
        errado, duplicata) -- diferente de corrigir_tipo_sanguineo(),
        que edita o valor mantendo o registro."""
        removido = self.tipo_sanguineo_repo.delete_by_uuid(uuid_observacao)
        if not removido:
            raise RecursoNaoEncontradoError(f"Observação de tipo sanguíneo não encontrada: {uuid_observacao}")
        return removido

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

    def anonimizar(self, uuid: str):
        """ALTERADO: delega para paciente.anonimizar() do model (já
        corrigido lá para de fato desligar PacienteDadosPessoais),
        em vez de duplicar essa lógica aqui com um db.session.delete
        manual -- uma só fonte de verdade para o que "anonimizar"
        significa."""
        paciente = self.buscar_por_uuid(uuid)
        if not paciente.pessoal:
            raise DadosInvalidosError("Paciente já está anonimizado.")

        cpf_plaintext = aes_decrypt(paciente.pessoal.cpf)
        paciente.anonimizar(cpf_plaintext)

        from src.models import db
        db.session.commit()
        return paciente
    
    