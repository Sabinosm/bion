"""leitura.py

Leitura de Paciente (só-leitura): busca por UUID, ID e CPF, listagem, resumo
paginado, contagens, dados pessoais descriptografados e prontuário completo.

Descriptografar nome e CPF é acesso a PII, então fica centralizado aqui, no
service, e nunca no controller. Depende de `self.repo`, definido no
PacienteService.
"""
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError
from src.core.security import aes_decrypt, hmac_sha256

from ...repositories.paciente_repository import POR_PAGINA_RESUMO
from .helpers import _normalizar


class LeituraMixin:
    """Leitura: busca, listagem, resumo, contagens, PII e prontuário."""

    POR_PAGINA_RESUMO = POR_PAGINA_RESUMO  # o controller calcula o offset com o mesmo valor

    def buscar_por_id(self, id: int):
        """Paciente pelo ID interno. Raises: RecursoNaoEncontradoError."""
        p = self.repo.find_by_id(id)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {id}")
        return p

    def buscar_por_uuid(self, uuid: str, id_empresa: int):
        """Paciente da empresa pelo UUID. Raises: RecursoNaoEncontradoError (404 uniforme)."""
        p = self.repo.find_by_uuid(uuid, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid}")
        return p

    def listar(self, id_empresa: int):
        """Todos os pacientes da empresa."""
        return self.repo.find_all(id_empresa)

    def _resumo_de(self, p) -> dict:
        """Paciente.to_dict_few com nome e início do CPF descriptografados."""
        nome = aes_decrypt(p.pessoal.nome_completo) if p.pessoal else None
        cpf_inicio = None
        if p.pessoal and p.pessoal.cpf:
            cpf_inicio = aes_decrypt(p.pessoal.cpf)[:4]
        return p.to_dict_few(nome_completo=nome, cpf_inicio=cpf_inicio)

    def listar_resumo(self, id_empresa: int, offset: int = 0, status: str = None,
                      sexo_biologico: str = None, q: str = None):
        """Listagem paginada no formato enxuto (to_dict_few).

        `q` (opcional): CPF completo (11 dígitos, busca exata pelo hash) ou parte do nome (sem
        distinção de acento ou maiúscula).
        """
        if q and q.strip():
            return self._buscar_resumo(id_empresa, q.strip(), offset, status, sexo_biologico)

        pacientes = self.repo.find_all_param(
            id_empresa=id_empresa, offset=offset, status=status,
            sexo_biologico=sexo_biologico,
        )
        return [self._resumo_de(p) for p in pacientes]

    def _buscar_resumo(self, id_empresa: int, q: str, offset: int, status, sexo_biologico):
        """Busca por CPF (hash, exata) ou por nome (em memória: o nome é cifrado e não dá para
        filtrar no banco). CPF parcial não é pesquisável, porque só existe o hash do CPF inteiro."""
        digitos = "".join(ch for ch in q if ch.isdigit())
        so_numerico = not any(ch.isalpha() for ch in q)

        if so_numerico and len(digitos) == 11:
            p = self.repo.find_por_cpf_hash(hmac_sha256(digitos), id_empresa)
            candidatos = [p] if p else []
        elif so_numerico:
            return []
        else:
            alvo = _normalizar(q)
            candidatos = [
                p for p in self.repo.find_all(id_empresa)
                if p.pessoal and alvo in _normalizar(aes_decrypt(p.pessoal.nome_completo))
            ]

        if status:
            candidatos = [p for p in candidatos if p.status == status]
        if sexo_biologico:
            candidatos = [p for p in candidatos if p.sexo_biologico == sexo_biologico]

        pagina = candidatos[offset:offset + self.POR_PAGINA_RESUMO]
        return [self._resumo_de(p) for p in pagina]

    def buscar_valido(self, uuid: str, id_empresa: int):
        """Paciente da empresa que PODE receber atendimento: 404 se não existe (mesmo 404 de
        'outra empresa'), 409 com o motivo se existe mas não é válido. Para abrir consulta."""
        return self.exigir_valido(self.buscar_por_uuid(uuid, id_empresa))

    @staticmethod
    def exigir_valido(paciente):
        """Guard para quem já carregou o paciente (ex.: Atendimento, que o obtém por atendimento ->
        consulta -> paciente). O critério único é Paciente.pode_receber_atendimento(); aqui só se
        escolhe a mensagem. Não vale para leitura de prontuário: histórico de falecido é consultável.

        Raises:
            ConflictoError: paciente com óbito registrado.
        """
        if paciente.pode_receber_atendimento():
            return paciente
        raise ConflictoError("Paciente com óbito registrado não pode receber atendimento.")

    def buscar_por_cpf(self, cpf_plaintext: str, id_empresa: int):
        """Paciente da empresa pelo CPF em texto claro (busca pelo hash). Raises: RecursoNaoEncontradoError."""
        p = self.repo.find_por_cpf_hash(hmac_sha256(cpf_plaintext), id_empresa)
        if not p:
            raise RecursoNaoEncontradoError("Paciente não encontrado para este CPF.")
        return p

    def count_pacientes_hoje(self, id_empresa):
        """Pacientes cadastrados hoje, no fuso da empresa."""
        return self.repo.count_pacientes_hoje(id_empresa=id_empresa)

    def count_pacientes(self, id_empresa):
        """Total de pacientes da empresa."""
        return self.repo.count_pacientes(id_empresa=id_empresa)

    def dados_pessoais_descriptografados(self, paciente):
        """Dados pessoais em texto claro (None se o paciente não tem, por não identificado ou
        anonimizado). Para o controller, quando o usuário pode ver PII."""
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

    def montar_prontuario_completo(self, uuid: str, id_empresa: int):
        """Paciente + todos os domínios clínicos num único dict, só para a tela de detalhe (nunca
        em listagem: cada domínio é uma query própria). A composição está em
        montar_prontuario_service.py. Só leitura."""
        from ..montar_prontuario_service import montar_prontuario_completo
        return montar_prontuario_completo(uuid, id_empresa)
