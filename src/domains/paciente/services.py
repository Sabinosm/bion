"""
Regras de negocio do dominio Paciente.

CORRECAO APLICADA: o controller original chamava `_svc.cadastrar(request.form.to_dict(), 1)`,
mas `PacienteService` nunca teve um metodo `cadastrar` -- so `buscar_por_uuid`
e `listar` (herdados do padrao generico repetido em quase todo o projeto
original). Implementado aqui de fato, incluindo a criptografia AES-256-GCM
dos campos de PII em `Paciente_pessoal` (o model ja sinalizava quais
campos deveriam ser cifrados via comentario `# AES-256`, mas nenhum
service chegou a chamar `aes_encrypt`/`aes_decrypt`).
"""

from datetime import datetime, timezone, date

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt, hmac_sha256
from .repositories import (
    PacienteRepository, AlergiaRepository, DoencaCronicaRepository,
    MedicamentoEmUsoRepository, ConsentimentoRepository,
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

    def cadastrar(self, dados: dict, id_usuario_cadastro: int):
        from src.database.paciente import Paciente, PacientePessoal

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
            tipo_sanguineo=dados.get("tipo_sanguineo"),
            data_nascimento=_parse_data(dados["data_nascimento"]),
            id_regiao_geografica=dados.get("id_regiao_geografica"),
            data_primeiro_atendimento=_parse_data(dados.get("data_primeiro_atendimento"))
            or datetime.now(timezone.utc).date(),
            cadastrado_por=id_usuario_cadastro,
        )
        self.repo.save(paciente)

        pessoal = PacientePessoal(
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
        from src.database import db
        db.session.add(pessoal)
        db.session.commit()

        return paciente

    def atualizar(self, uuid: str, dados: dict):
        paciente = self.buscar_por_uuid(uuid)
        if "tipo_sanguineo" in dados:
            paciente.tipo_sanguineo = dados["tipo_sanguineo"]
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

    def anonimizar(self, uuid: str):
        """Exclusão de dados pessoais mediante solicitação LGPD, preservando
        o registro clínico agregado (Paciente) de forma pseudoanonimizada."""
        paciente = self.buscar_por_uuid(uuid)
        if not paciente.pessoal:
            raise DadosInvalidosError("Paciente já está anonimizado.")

        cpf_plaintext = aes_decrypt(paciente.pessoal.cpf)
        paciente.identificacao_anonima = hmac_sha256(cpf_plaintext)

        from src.database import db
        db.session.delete(paciente.pessoal)
        db.session.commit()
        return paciente


class DadosClinicosService:
    """Alergias, doenças crônicas e medicamentos em uso do paciente."""

    def __init__(self):
        self.alergia_repo = AlergiaRepository()
        self.doenca_repo = DoencaCronicaRepository()
        self.medicamento_repo = MedicamentoEmUsoRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str):
        p = self.paciente_repo.find_by_uuid(uuid_paciente)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def listar_alergias(self, uuid_paciente: str):
        p = self._paciente_ou_404(uuid_paciente)
        return self.alergia_repo.find_por_paciente(p.id)

    def adicionar_alergia(self, uuid_paciente: str, dados: dict):
        from src.database.paciente import Alergia
        p = self._paciente_ou_404(uuid_paciente)
        if not dados.get("substancia") or not dados.get("tipo_reacao") or not dados.get("gravidade"):
            raise DadosInvalidosError("substancia, tipo_reacao e gravidade são obrigatórios.")
        a = Alergia(
            id_paciente=p.id,
            substancia=dados["substancia"],
            codigo_substancia=dados.get("codigo_substancia"),
            tipo_reacao=dados["tipo_reacao"],
            gravidade=dados["gravidade"],
            descricao_reacao=dados.get("descricao_reacao"),
            flag_confirmado=bool(dados.get("flag_confirmado", False)),
        )
        return self.alergia_repo.save(a)

    def listar_doencas(self, uuid_paciente: str):
        p = self._paciente_ou_404(uuid_paciente)
        return self.doenca_repo.find_por_paciente(p.id)

    def adicionar_doenca(self, uuid_paciente: str, dados: dict):
        from src.database.paciente import DoencaCronica
        p = self._paciente_ou_404(uuid_paciente)
        obrigatorios = ("codigo_cid10", "descricao_cid10", "desde", "status")
        faltando = [c for c in obrigatorios if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")
        d = DoencaCronica(
            id_paciente=p.id,
            codigo_cid10=dados["codigo_cid10"],
            descricao_cid10=dados["descricao_cid10"],
            desde=_parse_data(dados["desde"]),
            status=dados["status"],
            observacoes=dados.get("observacoes"),
        )
        return self.doenca_repo.save(d)

    def listar_medicamentos_em_uso(self, uuid_paciente: str):
        p = self._paciente_ou_404(uuid_paciente)
        return self.medicamento_repo.find_por_paciente(p.id)

    def adicionar_medicamento_em_uso(self, uuid_paciente: str, dados: dict):
        from src.database.paciente import MedicamentoEmUso
        p = self._paciente_ou_404(uuid_paciente)
        m = MedicamentoEmUso(
            id_paciente=p.id,
            id_catalogo=dados.get("id_catalogo"),
            descricao=dados.get("descricao"),
            dose=dados.get("dose"),
            frequencia=dados.get("frequencia"),
            desde=_parse_data(dados.get("desde")),
            flag_em_uso=bool(dados.get("flag_em_uso", True)),
        )
        return self.medicamento_repo.save(m)


class ConsentimentoService:
    """Consentimento LGPD do paciente (coleta, consulta e revogação)."""

    def __init__(self):
        self.repo = ConsentimentoRepository()
        self.paciente_repo = PacienteRepository()

    def _paciente_ou_404(self, uuid_paciente: str):
        p = self.paciente_repo.find_by_uuid(uuid_paciente)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    def listar_por_paciente(self, uuid_paciente: str):
        p = self._paciente_ou_404(uuid_paciente)
        return self.repo.find_por_paciente(p.id)

    def registrar(self, uuid_paciente: str, dados: dict, id_usuario_coletor: int):
        from src.database.paciente import Consentimento
        p = self._paciente_ou_404(uuid_paciente)
        obrigatorios = ("versao_termo", "canal_coleta")
        faltando = [c for c in obrigatorios if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")

        # Só pode haver um consentimento ativo por vez; revoga o anterior.
        ativo = self.repo.find_ativo_por_paciente(p.id)
        if ativo:
            ativo.status = "revogado"
            ativo.data_revogacao = datetime.now(timezone.utc)
            ativo.motivo_revogacao = "Substituído por novo termo de consentimento."
            self.repo.save(ativo)

        c = Consentimento(
            id_paciente=p.id,
            coletado_por=id_usuario_coletor,
            versao_termo=dados["versao_termo"],
            data_consentimento=datetime.now(timezone.utc),
            canal_coleta=dados["canal_coleta"],
            escopo_consentimento_json=dados.get("escopo_consentimento"),
            hash_documento=dados.get("hash_documento"),
        )
        return self.repo.save(c)

    def revogar(self, uuid_paciente: str, motivo: str = None):
        p = self._paciente_ou_404(uuid_paciente)
        ativo = self.repo.find_ativo_por_paciente(p.id)
        if not ativo:
            raise RecursoNaoEncontradoError("Não há consentimento ativo para este paciente.")
        ativo.status = "revogado"
        ativo.data_revogacao = datetime.now(timezone.utc)
        ativo.motivo_revogacao = motivo or "Revogado a pedido do titular."
        return self.repo.save(ativo)
