"""Repositório de acesso a dados da entidade OutputBion (resultados de IA)."""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.protocolos import OutputBion
from src.models.clinico import Consulta, Atendimento, ColetaClinica, InputProtocolo


class OutputBionRepository(IRepository[OutputBion]):
    """Encapsula todo acesso a dados de OutputBion via SQLAlchemy."""

    def find_by_id(self, id: int) -> Optional[OutputBion]:
        """Busca um OutputBion pelo ID interno (chave primária)."""
        return db.session.get(OutputBion, id)

    def find_by_uuid(self, uuid: str) -> Optional[OutputBion]:
        """Busca um OutputBion pelo UUID público exposto na API."""
        return OutputBion.query.filter_by(uuid=uuid).first()

    def save(self, entity: OutputBion) -> OutputBion:
        """Persiste (insert ou update) um OutputBion e commita a transação."""
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Remove um OutputBion pelo ID. Retorna False se não existir."""
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[OutputBion]:
        """Lista todos os OutputBion cadastrados, sem filtro."""
        return OutputBion.query.all()

    def find_output_triagem_da_consulta(self, uuid_consulta: str) -> Optional[OutputBion]:
        """
        Navega Consulta -> Atendimento(tipo=triagem) -> ColetaClinica ->
        InputProtocolo -> OutputBion mais recente. Usado pela tela de
        avaliação médica para reaproveitar o resultado já calculado pela
        IA na triagem, sem reprocessar.
        """
        consulta = Consulta.query.filter_by(uuid=uuid_consulta).first()
        if not consulta:
            return None

        atendimento_triagem = (
            Atendimento.query
            .filter_by(id_consulta=consulta.id, tipo_atendimento="triagem")
            .order_by(Atendimento.data_hora_inicio.desc())
            .first()
        )
        if not atendimento_triagem:
            return None

        coleta = (
            ColetaClinica.query
            .filter_by(id_atendimento=atendimento_triagem.id)
            .order_by(ColetaClinica.id.desc())
            .first()
        )
        if not coleta:
            return None

        input_protocolo = (
            InputProtocolo.query
            .filter_by(id_coleta_clinica=coleta.id)
            .order_by(InputProtocolo.id.desc())
            .first()
        )
        if not input_protocolo or not input_protocolo.outputs:
            return None

        return sorted(input_protocolo.outputs, key=lambda o: o.criado_em, reverse=True)[0]

    def _query_filtrada_empresa(self, id_empresa: int, dias: int):
        """Monta a base de query com os 4 joins até Usuario, reaproveitada
        por B1, B2 e B4 -- evita repetir o mesmo caminho 3 vezes.
 
        Caminho: OutputBion -> InputProtocolo -> ColetaClinica ->
        Atendimento -> realizado_por -> Usuario.
        """
        from datetime import datetime, timedelta, timezone
        from src.models.usuarios import Usuario
        from src.models.clinico import InputProtocolo, ColetaClinica, Atendimento
 
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
 
        return (
            db.session.query(OutputBion)
            .join(InputProtocolo, OutputBion.id_input == InputProtocolo.id)
            .join(ColetaClinica, InputProtocolo.id_coleta_clinica == ColetaClinica.id)
            .join(Atendimento, ColetaClinica.id_atendimento == Atendimento.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(OutputBion.criado_em >= limite)
        )
 
    # --- B1: Confiança média da IA ---
    def media_confianca(self, id_empresa: int, dias: int = 30) -> Optional[float]:
        """Média de indice_confianca no período. None se não houver dados."""
        from sqlalchemy import func
 
        media = (
            self._query_filtrada_empresa(id_empresa, dias)
            .with_entities(func.avg(OutputBion.indice_confianca))
            .scalar()
        )
        return float(media) if media is not None else None
 
    # --- B2: Completude média dos dados de entrada ---
    def media_completude(self, id_empresa: int, dias: int = 30) -> Optional[float]:
        """Média de indice_completude no período. None se não houver dados."""
        from sqlalchemy import func
 
        media = (
            self._query_filtrada_empresa(id_empresa, dias)
            .with_entities(func.avg(OutputBion.indice_completude))
            .scalar()
        )
        return float(media) if media is not None else None
 
    # --- B4: Versão do modelo de IA em uso ---
    def versoes_em_uso(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Contagem de outputs por versao_modelo_ia no período -- útil
        pra saber se ainda existem execuções em versão antiga durante
        um rollout gradual.
 
        Retorna: [{"versao_modelo_ia": "v2.3.1", "total": 140}, ...]
        """
        from sqlalchemy import func
 
        linhas = (
            self._query_filtrada_empresa(id_empresa, dias)
            .with_entities(
                OutputBion.versao_modelo_ia.label("versao"),
                func.count(OutputBion.id).label("total"),
            )
            .group_by(OutputBion.versao_modelo_ia)
            .order_by(func.count(OutputBion.id).desc())
            .all()
        )
        return [{"versao_modelo_ia": linha.versao, "total": linha.total} for linha in linhas]
 
    # --- E3: pares (completude, confianca) para correlação ---
    def pares_completude_confianca(self, id_empresa: int, dias: int = 30) -> list:
        """Lista de tuplas (indice_completude, indice_confianca) dos
        outputs no período, só os que têm AMBOS os valores preenchidos
        -- correlação não faz sentido com par incompleto.
        """
        linhas = (
            self._query_filtrada_empresa(id_empresa, dias)
            .filter(OutputBion.indice_completude.isnot(None))
            .filter(OutputBion.indice_confianca.isnot(None))
            .with_entities(OutputBion.indice_completude, OutputBion.indice_confianca)
            .all()
        )
        return [(float(c), float(cf)) for c, cf in linhas]
 