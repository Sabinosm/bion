"""Este arquivo concentra o acesso a dados de OutputBion usado pelas rotas de IA e pelas estatísticas.

Posse: o OutputBion não tem id_empresa. A empresa vem de OutputBion -> Atendimento -> Consulta.id_empresa.
Recurso inexistente e recurso de outra empresa produzem o mesmo resultado (None).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func

from src.core.interfaces import IRepository
from src.models import db
from src.models.clinico import Atendimento, ColetaClinica, Consulta, InputProtocolo
from src.models.protocolos import OutputBion


class OutputBionRepository(IRepository[OutputBion]):

    def find_by_id(self, id: int) -> Optional[OutputBion]:
        return db.session.get(OutputBion, id)

    def find_by_uuid(self, uuid: str, id_empresa: int) -> Optional[OutputBion]:
        """Esta função busca um OutputBion pelo UUID público, dentro da empresa informada."""
        return (
            db.session.query(OutputBion)
            .join(Atendimento, OutputBion.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(OutputBion.uuid == uuid, Consulta.id_empresa == id_empresa)
            .first()
        )

    def save(self, entity: OutputBion, commit: bool = True) -> OutputBion:
        db.session.add(entity)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return entity

    def delete(self, id: int) -> bool:
        raise NotImplementedError("OutputBion é insert-only e não é apagado fisicamente.")

    def find_atendimento_por_input(self, id_input_protocolo: int, id_empresa: int) -> Optional[Atendimento]:
        """Esta função resolve o Atendimento dono de um InputProtocolo pela cadeia InputProtocolo -> ColetaClinica -> Atendimento, dentro da empresa."""
        return (
            db.session.query(Atendimento)
            .join(ColetaClinica, ColetaClinica.id_atendimento == Atendimento.id)
            .join(InputProtocolo, InputProtocolo.id_coleta_clinica == ColetaClinica.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(InputProtocolo.id == id_input_protocolo, Consulta.id_empresa == id_empresa)
            .first()
        )

    def find_output_triagem_da_consulta(self, uuid_consulta: str, id_empresa: int) -> Optional[OutputBion]:
        """Esta função devolve o OutputBion vigente (o último envio) da triagem mais recente não cancelada da consulta, dentro da empresa."""
        triagem = (
            db.session.query(Atendimento)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(
                Consulta.uuid == uuid_consulta,
                Consulta.id_empresa == id_empresa,
                Atendimento.tipo_atendimento == "triagem",
                Atendimento.status != "cancelado",
            )
            .order_by(Atendimento.data_hora_inicio.desc(), Atendimento.id.desc())
            .first()
        )
        if triagem is None:
            return None
        return (
            db.session.query(OutputBion)
            .filter(OutputBion.id_atendimento == triagem.id)
            .order_by(OutputBion.criado_em.desc(), OutputBion.id.desc())
            .first()
        )

    def _base_empresa(self, id_empresa: int):
        return (
            db.session.query(OutputBion)
            .join(Atendimento, OutputBion.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Consulta.id_empresa == id_empresa)
        )

    def _query_filtrada_empresa(self, id_empresa: int, dias: int):
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        return self._base_empresa(id_empresa).filter(OutputBion.criado_em >= limite)

    def _query_periodo(self, id_empresa: int, data_inicio: datetime, data_fim: datetime):
        return self._base_empresa(id_empresa).filter(
            OutputBion.criado_em >= data_inicio, OutputBion.criado_em < data_fim
        )

    @staticmethod
    def _media(query, coluna) -> Optional[float]:
        media = query.with_entities(func.avg(coluna)).scalar()
        return float(media) if media is not None else None

    def media_confianca(self, id_empresa: int, dias: int = 30) -> Optional[float]:
        return self._media(self._query_filtrada_empresa(id_empresa, dias), OutputBion.indice_confianca)

    def media_confianca_periodo(self, id_empresa: int, data_inicio: datetime, data_fim: datetime) -> Optional[float]:
        return self._media(self._query_periodo(id_empresa, data_inicio, data_fim), OutputBion.indice_confianca)

    def media_completude(self, id_empresa: int, dias: int = 30) -> Optional[float]:
        return self._media(self._query_filtrada_empresa(id_empresa, dias), OutputBion.indice_completude)

    def media_completude_periodo(self, id_empresa: int, data_inicio: datetime, data_fim: datetime) -> Optional[float]:
        return self._media(self._query_periodo(id_empresa, data_inicio, data_fim), OutputBion.indice_completude)

    def versoes_em_uso(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Esta função conta os OutputBion com resposta por versao_modelo_ia no período. Formato: [{"versao_modelo_ia": ..., "total": ...}]."""
        linhas = (
            self._query_filtrada_empresa(id_empresa, dias)
            .filter(OutputBion.versao_modelo_ia.isnot(None))
            .with_entities(OutputBion.versao_modelo_ia.label("versao"), func.count(OutputBion.id).label("total"))
            .group_by(OutputBion.versao_modelo_ia)
            .order_by(func.count(OutputBion.id).desc())
            .all()
        )
        return [{"versao_modelo_ia": linha.versao, "total": linha.total} for linha in linhas]

    def pares_completude_confianca(self, id_empresa: int, dias: int = 30) -> list:
        linhas = (
            self._query_filtrada_empresa(id_empresa, dias)
            .filter(OutputBion.indice_completude.isnot(None), OutputBion.indice_confianca.isnot(None))
            .with_entities(OutputBion.indice_completude, OutputBion.indice_confianca)
            .all()
        )
        return [(float(c), float(cf)) for c, cf in linhas]

    def queixas_recentes(self, id_empresa: int, dias: int = 30, limite: int = 200) -> List[str]:
        limite_data = datetime.now(timezone.utc) - timedelta(days=dias)
        linhas = (
            db.session.query(InputProtocolo.queixa_principal)
            .join(ColetaClinica, InputProtocolo.id_coleta_clinica == ColetaClinica.id)
            .join(Atendimento, ColetaClinica.id_atendimento == Atendimento.id)
            .join(Consulta, Atendimento.id_consulta == Consulta.id)
            .filter(Consulta.id_empresa == id_empresa)
            .filter(Atendimento.data_hora_inicio >= limite_data)
            .filter(InputProtocolo.queixa_principal.isnot(None))
            .order_by(Atendimento.data_hora_inicio.desc())
            .limit(limite)
            .all()
        )
        return [linha[0] for linha in linhas if linha[0] and linha[0].strip()]
