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
