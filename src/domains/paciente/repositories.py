"""
Repositorios do dominio Paciente.

ALTERADO:
1. PacientePessoal -> PacienteDadosPessoais (renomeado, ver model).
2. AlergiaRepository ganhou find_reacoes_por_alergia (nova tabela
   ReacaoAlergia).
3. Novo ObservacaoTipoSanguineoRepository (nova tabela, extraída de
   Paciente.tipo_sanguineo).
"""

from typing import Optional, List

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (
    Paciente, PacienteDadosPessoais, Alergia, ReacaoAlergia,
    DoencaCronica, MedicamentoEmUso, Consentimento, ObservacaoTipoSanguineo,
)
from datetime import datetime, time, timezone, timedelta
from sqlalchemy import func

class PacienteRepository(IRepository[Paciente]):

    def find_by_id(self, id: int) -> Optional[Paciente]:
        return db.session.get(Paciente, id)

    def find_by_uuid(self, uuid: str) -> Optional[Paciente]:
        return Paciente.query.filter_by(uuid=uuid).first()

    def find_por_cpf_hash(self, cpf_hash: str) -> Optional[Paciente]:
        """Busca por CPF via hash HMAC-SHA256 (determinístico), não pelo
        valor cifrado com AES-256-GCM (ver nota original mantida)."""
        pessoal = PacienteDadosPessoais.query.filter_by(cpf_hash=cpf_hash).first()
        return pessoal.paciente if pessoal else None

    def save(self, entity: Paciente) -> Paciente:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def find_all(self) -> List[Paciente]:
        return Paciente.query.all()
    
    def count_pacientes_hoje(self, id_empresa: int) -> int:
            from src.models.usuarios import Usuario
            hoje = datetime.now(timezone.utc).date()
            inicio_dia = datetime.combine(hoje, time.min, tzinfo=timezone.utc)
            fim_dia = datetime.combine(hoje, time.max, tzinfo=timezone.utc)
    
            return (
                db.session.query(func.count(Paciente.id))
                .join(Usuario, Paciente.cadastrado_por == Usuario.id)
                .filter(Usuario.id_empresa == id_empresa)
                .filter(Paciente.criado_em >= inicio_dia)
                .filter(Paciente.criado_em < fim_dia)
                .scalar()
            )
            
    
    def count_pacientes(self, id_empresa: int) -> int:
        from src.models.usuarios import Usuario
            
        return (
                db.session.query(func.count(Paciente.id))
                .join(Usuario, Paciente.cadastrado_por == Usuario.id)
                .filter(Usuario.id_empresa == id_empresa)
                .scalar()
            )


class AlergiaRepository(IRepository[Alergia]):

    def find_by_id(self, id: int) -> Optional[Alergia]:
        return db.session.get(Alergia, id)

    def find_by_uuid(self, uuid: str) -> Optional[Alergia]:
        return Alergia.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Alergia]:
        return Alergia.query.filter_by(id_paciente=id_paciente).all()

    def save(self, entity: Alergia) -> Alergia:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def delete_by_uuid(self, uuid: str) -> bool:
        """Remove a alergia E suas reações associadas (cascade="all,
        delete-orphan" já configurado em Alergia.reacoes) -- forma mais
        comum de chamar isso a partir de uma rota HTTP."""
        e = self.find_by_uuid(uuid)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True


class ReacaoAlergiaRepository(IRepository[ReacaoAlergia]):
    """Novo -- suporta o histórico de reações (antes campos soltos em Alergia)."""

    def find_by_id(self, id: int) -> Optional[ReacaoAlergia]:
        return db.session.get(ReacaoAlergia, id)

    def find_by_uuid(self, uuid: str) -> Optional[ReacaoAlergia]:
        return ReacaoAlergia.query.filter_by(uuid=uuid).first()

    def find_por_alergia(self, id_alergia: int) -> List[ReacaoAlergia]:
        return ReacaoAlergia.query.filter_by(id_alergia=id_alergia).all()

    def save(self, entity: ReacaoAlergia) -> ReacaoAlergia:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def delete_by_uuid(self, uuid: str) -> bool:
        """Remove APENAS esta reação específica, preservando a Alergia
        e as demais reações do histórico -- diferente de
        AlergiaRepository.delete_by_uuid(), que apaga tudo."""
        e = self.find_by_uuid(uuid)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True


class DoencaCronicaRepository(IRepository[DoencaCronica]):

    def find_by_id(self, id: int) -> Optional[DoencaCronica]:
        return db.session.get(DoencaCronica, id)

    def find_by_uuid(self, uuid: str) -> Optional[DoencaCronica]:
        return DoencaCronica.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[DoencaCronica]:
        return DoencaCronica.query.filter_by(id_paciente=id_paciente).all()

    def save(self, entity: DoencaCronica) -> DoencaCronica:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True


class MedicamentoEmUsoRepository(IRepository[MedicamentoEmUso]):

    def find_by_id(self, id: int) -> Optional[MedicamentoEmUso]:
        return db.session.get(MedicamentoEmUso, id)

    def find_by_uuid(self, uuid: str) -> Optional[MedicamentoEmUso]:
        # ALTERADO: agora existe uuid de verdade (era None antes, por
        # falta da coluna -- ver 08_medicamentos_em_uso_migration.sql)
        return MedicamentoEmUso.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[MedicamentoEmUso]:
        return MedicamentoEmUso.query.filter_by(id_paciente=id_paciente).all()

    def save(self, entity: MedicamentoEmUso) -> MedicamentoEmUso:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True


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


class ConsentimentoRepository(IRepository[Consentimento]):

    def find_by_id(self, id: int) -> Optional[Consentimento]:
        return db.session.get(Consentimento, id)

    def find_by_uuid(self, uuid: str) -> Optional[Consentimento]:
        return Consentimento.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[Consentimento]:
        return Consentimento.query.filter_by(id_paciente=id_paciente).all()

    def find_ativo_por_paciente(self, id_paciente: int) -> Optional[Consentimento]:
        return Consentimento.query.filter_by(id_paciente=id_paciente, status="ativo").first()

    def save(self, entity: Consentimento) -> Consentimento:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True
    


    