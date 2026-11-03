"""prescricao_repository.py

Acesso a dados dos medicamentos prescritos (Prescricao): busca dentro de um
resultado, ids de catálogo já prescritos e controle de transação, além das
agregações do ranking de medicamentos prescritos por classe farmacêutica usado
pelas estatísticas.

A transação segue o padrão dos demais repositórios: salvar, remover, confirmar
e desfazer, com commit desligado só fazendo flush (o fluxo da IA grava tudo num
commit único no fim). As agregações contam só prescrições de resultados
CONFIRMADOS e filtram a empresa pela Consulta do atendimento, um dado que não
muda, e não pelo usuário que realizou.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Set

from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import Prescricao, ResultadoPrescricao, Atendimento, Consulta


class PrescricaoRepository(IRepository[Prescricao]):

    # ------------------------------------------------------------ transação
    def confirmar(self, commit: bool = True) -> None:
        """commit=True: commita; commit=False: só flush (a transação segue aberta)."""
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    # ---------------------------------------------------------------- leitura
    def find_by_id(self, id: int) -> Optional[Prescricao]:
        return db.session.get(Prescricao, id)

    def find_by_uuid(self, uuid: str) -> Optional[Prescricao]:
        return Prescricao.query.filter_by(uuid=uuid).first()

    def find_do_resultado(self, uuid: str, id_resultado: int) -> Optional[Prescricao]:
        """Item só é encontrado se pertencer ao resultado informado."""
        return Prescricao.query.filter_by(uuid=uuid, id_resultado_prescricao=id_resultado).first()

    def ids_catalogo_do_resultado(self, id_resultado: int) -> Set[int]:
        """Ids de CatalogoMedicamentos já prescritos no resultado (base da checagem de repetição
        e da verificação de interações)."""
        linhas = (
            db.session.query(Prescricao.id_catalogo)
            .filter(Prescricao.id_resultado_prescricao == id_resultado)
            .all()
        )
        return {linha[0] for linha in linhas if linha[0] is not None}

    def find_all(self) -> List[Prescricao]:
        return Prescricao.query.all()

    # --------------------------------------------------------------- escrita
    def save(self, entity: Prescricao, commit: bool = True) -> Prescricao:
        """Persiste (insert ou update). commit=False só faz flush: gera ids sem fechar a transação."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def remover(self, entity: Prescricao, commit: bool = True) -> None:
        """Remove o item já carregado (commit=False deixa a transação com o chamador)."""
        db.session.delete(entity)
        self.confirmar(commit)

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        self.remover(e)
        return True

    # ------------------------------------------------------------ estatísticas
    @staticmethod
    def _prescricoes_confirmadas(colunas: tuple, id_empresa: int, dias: int):
        """Base das agregações: prescrições de resultados confirmados nos últimos `dias`, das Consultas
        da empresa, já juntadas ao catálogo de medicamentos."""
        from src.models.catalogos import CatalogoMedicamentos

        limite_data = datetime.now(timezone.utc) - timedelta(days=dias)
        return (
            db.session.query(*colunas)
            .select_from(Prescricao)
            .join(CatalogoMedicamentos, Prescricao.id_catalogo == CatalogoMedicamentos.id)
            .join(ResultadoPrescricao, Prescricao.id_resultado_prescricao == ResultadoPrescricao.id)
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Consulta.id_empresa == id_empresa)
            .filter(ResultadoPrescricao.data_hora_formulacao >= limite_data)
            .filter(ResultadoPrescricao.status == "confirmado")
        )

    def top_por_classe(self, id_empresa: int, dias: int = 30, limite: int = 10) -> List[dict]:
        """Ranking de classes farmacêuticas mais prescritas.

        Caminho: Prescricao -> ResultadoPrescricao -> Atendimento -> Consulta (empresa); e
        Prescricao -> CatalogoMedicamentos para a classe.

        Retorna: [{"classe_farmaceutica": "Analgésico", "total": 58}, ...]
        """
        from src.models.catalogos import CatalogoMedicamentos

        linhas = (
            self._prescricoes_confirmadas(
                (CatalogoMedicamentos.classe_farmaceutica.label("classe"),
                 func.count(Prescricao.id).label("total")),
                id_empresa, dias,
            )
            .filter(CatalogoMedicamentos.classe_farmaceutica.isnot(None))
            .group_by(CatalogoMedicamentos.classe_farmaceutica)
            .order_by(func.count(Prescricao.id).desc())
            .limit(limite)
            .all()
        )
        return [{"classe_farmaceutica": linha.classe, "total": linha.total} for linha in linhas]

    def top_principios_ativos_por_classe(self, id_empresa: int, classe: str,
                                         dias: int = 30, limite: int = 10) -> List[dict]:
        """Detalhe do ranking de classes: quando o usuário clica numa classe no gráfico, mostra
        quais princípios ativos específicos compõem aquele total.

        Retorna: [{"principio_ativo": "Dipirona", "total": 31}, ...]
        """
        from src.models.catalogos import CatalogoMedicamentos

        linhas = (
            self._prescricoes_confirmadas(
                (CatalogoMedicamentos.principio_ativo.label("principio_ativo"),
                 func.count(Prescricao.id).label("total")),
                id_empresa, dias,
            )
            .filter(CatalogoMedicamentos.classe_farmaceutica == classe)
            .group_by(CatalogoMedicamentos.principio_ativo)
            .order_by(func.count(Prescricao.id).desc())
            .limit(limite)
            .all()
        )
        return [{"principio_ativo": linha.principio_ativo, "total": linha.total} for linha in linhas]
