"""prescricao_exame_repository.py

Acesso a dados dos exames prescritos (PrescricaoExame): busca dentro de um
resultado, controle de transação, busca do exame no catálogo e a agregação de
urgência por origem (IA x profissional) usada pelas estatísticas.

A transação segue o padrão dos demais repositórios: salvar, remover, confirmar
e desfazer, com commit desligado só fazendo flush (o fluxo da IA grava tudo num
commit único no fim). A agregação conta só exames de resultados CONFIRMADOS e
filtra a empresa pela Consulta do atendimento, um dado que não muda.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List

from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.clinico import PrescricaoExame, ResultadoPrescricao, Atendimento, Consulta


class PrescricaoExameRepository(IRepository[PrescricaoExame]):

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
    def find_by_id(self, id: int) -> Optional[PrescricaoExame]:
        return db.session.get(PrescricaoExame, id)

    def find_by_uuid(self, uuid: str) -> Optional[PrescricaoExame]:
        return PrescricaoExame.query.filter_by(uuid=uuid).first()

    def find_do_resultado(self, uuid: str, id_resultado: int) -> Optional[PrescricaoExame]:
        """Item só é encontrado se pertencer ao resultado informado."""
        return PrescricaoExame.query.filter_by(uuid=uuid, id_resultado=id_resultado).first()

    def ids_exame_do_resultado(self, id_resultado: int) -> set:
        """Ids do catálogo de exames já prescritos no resultado (base da checagem de repetição)."""
        linhas = (
            db.session.query(PrescricaoExame.id_exame)
            .filter(PrescricaoExame.id_resultado == id_resultado)
            .all()
        )
        return {linha[0] for linha in linhas if linha[0] is not None}

    def find_catalogo_por_uuid(self, uuid: str):
        """Exame do catálogo pelo UUID público (o catálogo é global, sem filtro de empresa). Quando
        existir um repositório do catálogo de exames, esta busca passa a viver nele."""
        from src.models.catalogos import CatalogoExames
        return CatalogoExames.query.filter_by(uuid=uuid).first()

    def find_all(self) -> List[PrescricaoExame]:
        return PrescricaoExame.query.all()

    # --------------------------------------------------------------- escrita
    def save(self, entity: PrescricaoExame, commit: bool = True) -> PrescricaoExame:
        """Persiste (insert ou update). commit=False só faz flush: gera ids sem fechar a transação."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def remover(self, entity: PrescricaoExame, commit: bool = True) -> None:
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
    def urgencia_por_origem(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Contagem de exames prescritos cruzando urgência x origem da sugestão (IA x profissional),
        dos resultados confirmados das Consultas da empresa, criados nos últimos `dias`.

        Retorna: [{"urgencia": "urgente", "origem_sugestao": "bion_ia", "total": 26}, ...]
        """
        limite = datetime.now(timezone.utc) - timedelta(days=dias)

        linhas = (
            db.session.query(
                PrescricaoExame.urgencia.label("urgencia"),
                PrescricaoExame.origem_sugestao.label("origem_sugestao"),
                func.count(PrescricaoExame.id).label("total"),
            )
            .join(ResultadoPrescricao, PrescricaoExame.id_resultado == ResultadoPrescricao.id)
            .join(Atendimento, ResultadoPrescricao.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Consulta.id_empresa == id_empresa)
            .filter(ResultadoPrescricao.status == "confirmado")
            .filter(PrescricaoExame.criado_em >= limite)
            .group_by(PrescricaoExame.urgencia, PrescricaoExame.origem_sugestao)
            .all()
        )
        return [
            {"urgencia": linha.urgencia, "origem_sugestao": linha.origem_sugestao, "total": linha.total}
            for linha in linhas
        ]
