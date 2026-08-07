"""
Regras de negocio do dominio Paciente.

ALTERADO nesta migração:
1. PacientePessoal -> PacienteDadosPessoais (renomeado).
2. Paciente(tipo_sanguineo=...) REMOVIDO do construtor -- agora dois
   métodos distintos: registrar_tipo_sanguineo() (novo exame/resultado,
   preserva histórico) e corrigir_tipo_sanguineo() (edita um registro
   específico, uso: correção de erro de digitação).
3. Alergia(tipo_reacao=..., gravidade=...) REMOVIDO do construtor --
   agora Alergia guarda só substancia/codigo, e adicionar_alergia()
   cria a Alergia + a primeira ReacaoAlergia numa única chamada.
4. anonimizar() usa paciente.anonimizar() do model (já corrigido lá)
   em vez de fazer isso solto aqui -- evita duplicar a lógica em dois
   lugares.
"""

from datetime import datetime, timezone, date

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError, ConflictoError
from src.core.security import aes_encrypt, aes_decrypt, hmac_sha256
from .repositories import (
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


class DadosClinicosService:
    """Alergias, doenças crônicas e medicamentos em uso do paciente."""

    def __init__(self):
        self.alergia_repo = AlergiaRepository()
        self.reacao_repo = ReacaoAlergiaRepository()
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
        """ALTERADO: Alergia não recebe mais tipo_reacao/gravidade no
        construtor -- esses campos agora criam a PRIMEIRA ReacaoAlergia
        associada, na mesma chamada (o contrato de entrada da API não
        muda: o cliente continua mandando os mesmos campos de sempre)."""
        from src.models.pacientes import Alergia
        p = self._paciente_ou_404(uuid_paciente)
        if not dados.get("substancia") or not dados.get("tipo_reacao") or not dados.get("gravidade"):
            raise DadosInvalidosError("substancia, tipo_reacao e gravidade são obrigatórios.")

        a = Alergia(
            id_paciente=p.id,
            substancia=dados["substancia"],
            codigo_substancia=dados.get("codigo_substancia"),
            flag_confirmado=bool(dados.get("flag_confirmado", False)),
        )
        a.registrar_reacao(
            manifestacao=dados["tipo_reacao"],
            gravidade=dados["gravidade"],
            descricao=dados.get("descricao_reacao"),
        )
        return self.alergia_repo.save(a)

    def adicionar_reacao(self, uuid_alergia: str, dados: dict):
        """NOVO: registra reação adicional numa alergia já existente
        (histórico de ocorrências) -- caminho que não existia antes,
        já que o schema antigo só suportava uma reação por alergia."""
        alergia = self.alergia_repo.find_by_uuid(uuid_alergia)
        if not alergia:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        if not dados.get("manifestacao") or not dados.get("gravidade"):
            raise DadosInvalidosError("manifestacao e gravidade são obrigatórios.")
        alergia.registrar_reacao(
            manifestacao=dados["manifestacao"],
            gravidade=dados["gravidade"],
            descricao=dados.get("descricao"),
            data_ocorrencia=_parse_data(dados.get("data_ocorrencia")),
        )
        return self.alergia_repo.save(alergia)

    def remover_alergia(self, uuid_alergia: str):
        """Remove a alergia inteira, incluindo todo o histórico de
        reações associadas (cascade já configurado no model)."""
        removido = self.alergia_repo.delete_by_uuid(uuid_alergia)
        if not removido:
            raise RecursoNaoEncontradoError(f"Alergia não encontrada: {uuid_alergia}")
        return removido

    def remover_reacao(self, uuid_reacao: str):
        """Remove APENAS uma reação específica do histórico, mantendo a
        Alergia e as demais reações intactas -- uso: reação registrada
        por engano, diferente de remover a alergia toda."""
        removido = self.reacao_repo.delete_by_uuid(uuid_reacao)
        if not removido:
            raise RecursoNaoEncontradoError(f"Reação não encontrada: {uuid_reacao}")
        return removido

    def listar_doencas(self, uuid_paciente: str):
        p = self._paciente_ou_404(uuid_paciente)
        return self.doenca_repo.find_por_paciente(p.id)

    def adicionar_doenca(self, uuid_paciente: str, dados: dict):
        from src.models.pacientes import DoencaCronica
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
        from src.models.pacientes import MedicamentoEmUso
        p = self._paciente_ou_404(uuid_paciente)
        m = MedicamentoEmUso(
            id_paciente=p.id,
            id_catalogo=dados.get("id_catalogo"),
            descricao=dados.get("descricao"),
            dose=dados.get("dose"),
            frequencia=dados.get("frequencia"),
            desde=_parse_data(dados.get("desde")),
            flag_em_uso=bool(dados.get("flag_em_uso", True)),
            status_uso=dados.get("status_uso", "ativo" if dados.get("flag_em_uso", True) else "interrompido"),
        )
        return self.medicamento_repo.save(m)


class ConsentimentoService:
    """SEM ALTERAÇÃO -- Consentimento não foi tocado nesta migração."""

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
        from src.models.pacientes import Consentimento
        p = self._paciente_ou_404(uuid_paciente)
        obrigatorios = ("versao_termo", "canal_coleta")
        faltando = [c for c in obrigatorios if not dados.get(c)]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes: {', '.join(faltando)}")

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