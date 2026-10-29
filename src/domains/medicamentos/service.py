from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from .repository import CatalogoMedicamentosRepository
from .interacoes.interacoes_medicamento_repository import InteracoesMedicamentosRepository

MAX_CONTRAINDICACOES_FILTRO = 10
MAX_MEDICAMENTOS_VERIFICACAO = 30


def _unicos(valores):
    """Remove vazios e repetidos, mantendo a ordem."""
    return list(dict.fromkeys(v.strip() for v in (valores or []) if v and v.strip()))


class CatalogoMedicamentosService:

    def __init__(self):
        self.repo = CatalogoMedicamentosRepository()
        self.repo_interacoes = InteracoesMedicamentosRepository()

    def buscar_por_uuid(self, uuid: str):
        m = self.repo.find_by_uuid(uuid)
        if not m:
            raise RecursoNaoEncontradoError(f"Medicamento não encontrado: {uuid}")
        return m

    def listar(self):
        return self.repo.find_all()

    def buscar(self, termo: str):
        return self.repo.buscar_por_principio_ativo(termo)

    def listar_classes(self):
        """Classes farmacêuticas existentes no catálogo (para o filtro do front)."""
        return self.repo.listar_classes()

    def listar_paginado(self, termo, pagina: int, por_pagina: int,
                        uuid_indicacao=None, uuids_sem_contraindicacao=None, classe=None):
        """Busca do médico.

        termo: princípio ativo, sinônimo ou nome comercial.
        uuid_indicacao: só medicamentos indicados para essa condição/sintoma.
        uuids_sem_contraindicacao: exclui os contraindicados em QUALQUER dessas condições.
        classe: classe farmacêutica exata (valor vindo de listar_classes).

        Filtro de segurança com uuid inexistente é erro (404), nunca ignorado:
        ignorar deixaria passar justamente os medicamentos que o médico quis excluir."""
        uuid_indicacao = (uuid_indicacao or "").strip() or None
        uuids = _unicos(uuids_sem_contraindicacao)
        classe = (classe or "").strip() or None

        if len(uuids) > MAX_CONTRAINDICACOES_FILTRO:
            raise DadosInvalidosError(
                f"Informe no máximo {MAX_CONTRAINDICACOES_FILTRO} contraindicações no filtro.")
        if uuid_indicacao and not self.repo.existe_indicacao(uuid_indicacao):
            raise RecursoNaoEncontradoError(f"Indicação terapêutica não encontrada: {uuid_indicacao}")
        if uuids:
            existentes = self.repo.uuids_contraindicacao_existentes(uuids)
            faltando = [u for u in uuids if u not in existentes]
            if faltando:
                raise RecursoNaoEncontradoError(f"Contraindicação não encontrada: {', '.join(faltando)}")

        return self.repo.listar_paginado(termo, pagina, por_pagina, uuid_indicacao, uuids, classe)

    def verificar_interacoes(self, uuid: str) -> dict:
        """Interações cadastradas para o medicamento + total da base.

        O total acompanha o resultado para que quem consome (médico,
        IA) consiga distinguir "sem interação cadastrada" de "base
        ainda vazia/parcial" -- lista vazia sozinha não prova ausência
        de interação clínica."""
        m = self.buscar_por_uuid(uuid)
        return {
            "medicamento": m,
            "interacoes": self.repo_interacoes.find_por_medicamento(m.id),
            "total_na_base": self.repo_interacoes.contar(),
        }

    def verificar_interacoes_entre(self, uuids) -> dict:
        """Interações entre os medicamentos informados (todos contra todos).

        Uso no atendimento: o front envia o medicamento que está sendo prescrito
        mais os que o paciente já usa. Mesma regra de cobertura: lista vazia não
        prova ausência de interação clínica."""
        uuids = _unicos(uuids)
        if len(uuids) < 2:
            raise DadosInvalidosError("Informe ao menos 2 medicamentos para verificar interações.")
        if len(uuids) > MAX_MEDICAMENTOS_VERIFICACAO:
            raise DadosInvalidosError(
                f"Informe no máximo {MAX_MEDICAMENTOS_VERIFICACAO} medicamentos por verificação.")

        medicamentos = self.repo.find_by_uuids(uuids)
        achados = {m.uuid for m in medicamentos}
        faltando = [u for u in uuids if u not in achados]
        if faltando:
            raise RecursoNaoEncontradoError(f"Medicamento não encontrado: {', '.join(faltando)}")

        return {
            "medicamentos": medicamentos,
            "interacoes": self.repo_interacoes.find_entre_medicamentos([m.id for m in medicamentos]),
            "total_na_base": self.repo_interacoes.contar(),
        }