from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (
    Paciente, PacienteDadosPessoais, Alergia, ReacaoAlergia,
    DoencaCronica, MedicamentoEmUso, Consentimento, ObservacaoTipoSanguineo,
)
from datetime import datetime, time, timezone, timedelta
from sqlalchemy import func

class ObservacaoTipoSanguineoRepository(IRepository[ObservacaoTipoSanguineo]):
    """Novo -- extraído de Paciente.tipo_sanguineo.

    Dois caminhos de escrita, deliberadamente separados:
      - save() / find_mais_recente_por_paciente(): fluxo de REGISTRO
        (novo exame, nova observação, preserva histórico).
      - corrigir(): fluxo de CORREÇÃO (edita uma observação específica
        já existente, identificada por uuid -- usado quando o dado foi
        digitado errado, não quando há um novo resultado clínico).
    """

    def find_by_id(self, id: int) -> Optional[ObservacaoTipoSanguineo]:
        return db.session.get(ObservacaoTipoSanguineo, id)

    def find_by_uuid(self, uuid: str) -> Optional[ObservacaoTipoSanguineo]:
        return ObservacaoTipoSanguineo.query.filter_by(uuid=uuid).first()

    def find_mais_recente_por_paciente(self, id_paciente: int) -> Optional[ObservacaoTipoSanguineo]:
        return (
            ObservacaoTipoSanguineo.query
            .filter_by(id_paciente=id_paciente)
            .order_by(ObservacaoTipoSanguineo.data_registro.desc())
            .first()
        )

    def save(self, entity: ObservacaoTipoSanguineo) -> ObservacaoTipoSanguineo:
        db.session.add(entity)
        db.session.commit()
        return entity

    def corrigir(self, uuid_observacao: str, novo_valor: str) -> Optional[ObservacaoTipoSanguineo]:
        """Edita o VALOR de uma observação já existente, sem criar uma
        nova linha nem alterar data_registro -- uso: corrigir erro de
        digitação, não registrar novo resultado."""
        obs = self.find_by_uuid(uuid_observacao)
        if not obs:
            return None
        obs.tipo_sanguineo = novo_valor
        db.session.commit()
        return obs

    def delete(self, id: int) -> bool:
        """Remove uma observação de tipo sanguíneo pelo ID.

        Uso esperado: correção de um registro criado por engano (ex:
        paciente errado, duplicata) -- não confundir com 'atualizar o
        tipo sanguíneo', que tem os caminhos registrar()/corrigir()
        acima. Deletar remove o histórico daquele ponto, então normalmente
        só admin ou o próprio autor do registro deveria poder fazer isso
        (decisão de autorização fica na camada de service/controller).
        """
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def delete_by_uuid(self, uuid_observacao: str) -> bool:
        """Mesma operação que delete(), mas pelo UUID público -- forma
        mais comum de chamar isso a partir de uma rota HTTP, já que o
        id interno nunca é exposto na API."""
        e = self.find_by_uuid(uuid_observacao)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True
    
    # --- F3: Distribuição de tipo sanguíneo na base ---
    def distribuicao_tipo_sanguineo(self, id_empresa: int) -> dict:
        """Distribuição por tipo_sanguineo, usando só a observação MAIS
        RECENTE de cada paciente (não conta duplicado se o paciente tem
        várias observações no histórico).
 
        Usa uma subquery de MAX(data_registro) por paciente, depois
        junta de volta pra pegar o tipo_sanguineo daquela observação
        específica -- evita trazer todo o histórico pra agregar em Python.
 
        Retorna: {"O+": 120, "A+": 95, ...}
        """
        from src.models import db
        from sqlalchemy import func
        from src.models.usuarios import Usuario
        from src.models.pacientes import Paciente
 
        # subquery: data da observação mais recente por paciente
        subq = (
            db.session.query(
                ObservacaoTipoSanguineo.id_paciente.label("id_paciente"),
                func.max(ObservacaoTipoSanguineo.data_registro).label("max_data"),
            )
            .group_by(ObservacaoTipoSanguineo.id_paciente)
            .subquery()
        )
 
        linhas = (
            db.session.query(
                ObservacaoTipoSanguineo.tipo_sanguineo.label("tipo"),
                func.count(ObservacaoTipoSanguineo.id).label("total"),
            )
            .join(
                subq,
                (ObservacaoTipoSanguineo.id_paciente == subq.c.id_paciente)
                & (ObservacaoTipoSanguineo.data_registro == subq.c.max_data),
            )
            .join(Paciente, ObservacaoTipoSanguineo.id_paciente == Paciente.id)
            .join(Usuario, Paciente.cadastrado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .group_by(ObservacaoTipoSanguineo.tipo_sanguineo)
            .all()
        )
        return {linha.tipo: linha.total for linha in linhas}