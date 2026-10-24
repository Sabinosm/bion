"""Leitura de Paciente: busca por uuid/CPF, listagem, resumo paginado, contagens,
PII descriptografada e prontuário completo (tudo só-leitura).

Depende de `self.repo` (definido em PacienteService.__init__).
"""
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError
from src.core.security import aes_decrypt, hmac_sha256

from .helpers import _normalizar


class LeituraMixin:
    """Leitura: busca, listagem, resumo, contagens, PII e prontuário."""

    POR_PAGINA_RESUMO = 8  # mesmo valor que o controller usa (pagina * 8)

    def buscar_por_id(self, id:int):
        p = self.repo.find_by_id(id)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {id}")
        return p
    
    def buscar_por_uuid(self, uuid: str, id_empresa: int):
        p = self.repo.find_by_uuid(uuid, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid}")
        return p

    def listar(self, id_empresa: int):
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
        """Listagem paginada já no formato enxuto (to_dict_few).
        Fica aqui e não no controller porque descriptografar nome/CPF
        é acesso a PII -- centralizado no service.

        `q` (opcional): CPF completo (11 dígitos, busca exata pelo hash)
        ou parte do nome (sem distinção de acento/maiúscula)."""
        if q and q.strip():
            return self._buscar_resumo(id_empresa, q.strip(), offset, status, sexo_biologico)

        pacientes = self.repo.find_all_param(
            id_empresa=id_empresa, offset=offset, status=status,
            sexo_biologico=sexo_biologico,
        )
        return [self._resumo_de(p) for p in pacientes]

    def _buscar_resumo(self, id_empresa: int, q: str, offset: int, status, sexo_biologico):
        digitos = "".join(ch for ch in q if ch.isdigit())
        so_numerico = not any(ch.isalpha() for ch in q)

        if so_numerico and len(digitos) == 11:
            p = self.repo.find_por_cpf_hash(hmac_sha256(digitos), id_empresa)
            candidatos = [p] if p else []
        elif so_numerico:
            return []  # CPF parcial não é pesquisável (só existe o hash do CPF inteiro)
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
        from ..montar_prontuario_service import montar_prontuario_completo
        return montar_prontuario_completo(uuid, id_empresa)
