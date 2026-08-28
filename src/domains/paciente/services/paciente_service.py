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
            id_empresa=id_empresa,
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
    

    def atualizar(self, uuid: str, dados: dict, id_empresa: int):
        """ALTERADO: tipo_sanguineo SAIU daqui -- ver
        registrar_tipo_sanguineo() e corrigir_tipo_sanguineo() abaixo,
        que são os pontos de entrada corretos agora (a rota decide
        qual chamar, conforme a intenção: novo exame vs correção).

        ALTERADO: exige id_empresa -- buscar_por_uuid já garante que só
        se pode atualizar paciente da própria empresa (levanta 404 em
        vez de vazar que o UUID pertence a outro tenant)."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)
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
        """ALTERADO: delega para paciente.anonimizar() do model (já
        corrigido lá para de fato desligar PacienteDadosPessoais),
        em vez de duplicar essa lógica aqui com um db.session.delete
        manual -- uma só fonte de verdade para o que "anonimizar"
        significa.

        ALTERADO: exige id_empresa pelo mesmo motivo de atualizar()."""
        paciente = self.buscar_por_uuid(uuid, id_empresa)
        if not paciente.pessoal:
            raise DadosInvalidosError("Paciente já está anonimizado.")

        cpf_plaintext = aes_decrypt(paciente.pessoal.cpf)
        paciente.anonimizar(cpf_plaintext)

        from src.models import db
        db.session.commit()
        return paciente