from typing import Optional, List
from datetime import datetime, timezone

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import DoencaCronica, Paciente
from sqlalchemy import func

class DoencaCronicaRepository(IRepository[DoencaCronica]):
    """Toda leitura "normal" (find_by_id, find_by_uuid, find_por_paciente,
    top_cid_ativas) filtra `deletado == False` por padrão -- doença
    soft-deletada não deve aparecer em nenhuma consulta comum. O único
    jeito de ver registros removidos é find_apagados, que faz o
    inverso (só traz deletados). Não existe find_todos que ignore o
    filtro -- se precisar disso no futuro (ex.: export de auditoria
    completo), adicione um método novo e explícito em vez de flag
    opcional aqui, pra não arriscar um "esqueci de passar True" vazando
    dado removido pra alguma rota."""

    def find_by_id(self, id: int) -> Optional[DoencaCronica]:
        return (
            DoencaCronica.query
            .filter(DoencaCronica.id == id, DoencaCronica.deletado == False)
            .first()
        )

    def find_by_uuid(self, uuid: str) -> Optional[DoencaCronica]:
        return (
            DoencaCronica.query
            .filter(DoencaCronica.uuid == uuid, DoencaCronica.deletado == False)
            .first()
        )

    def find_by_uuid_incluindo_deletados(self, uuid: str) -> Optional[DoencaCronica]:
        """NOVO: busca por uuid SEM filtrar deletado -- usado quando a
        camada de service precisa distinguir 'não existe' de 'existe
        mas está soft-deletado' (ex.: atualizar_doenca bloqueando
        edição em registro removido com um erro explícito, em vez de
        um 404 genérico que esconderia a causa; restaurar_doenca
        também precisa achar o registro justamente porque ele está
        deletado). Não usar para listagens/consultas comuns -- para
        isso, find_by_uuid (filtrado) é o correto."""
        return DoencaCronica.query.filter_by(uuid=uuid).first()

    def find_por_paciente(self, id_paciente: int) -> List[DoencaCronica]:
        return (
            DoencaCronica.query
            .filter(DoencaCronica.id_paciente == id_paciente, DoencaCronica.deletado == False)
            .all()
        )

    def find_apagados(self, id_paciente: Optional[int] = None) -> List[DoencaCronica]:
        """NOVO: único ponto de acesso a registros soft-deletados.
        id_paciente opcional -- sem ele, lista todos os deletados
        (uso de auditoria/admin); com ele, filtra por paciente (uso
        equivalente ao find_por_paciente, mas para a lixeira). O status
        clínico (ativa/em-remissao) do registro continua intacto aqui
        -- é lido normalmente em to_dict(), já que só `deletado`
        controla a visibilidade."""
        query = DoencaCronica.query.filter(DoencaCronica.deletado == True)
        if id_paciente is not None:
            query = query.filter(DoencaCronica.id_paciente == id_paciente)
        return query.all()

    def save(self, entity: DoencaCronica) -> DoencaCronica:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: int) -> bool:
        """Mantido só por contrato com IRepository -- delete físico.
        NÃO deve ser chamado pela camada de service/controller de
        doença crônica; use soft_delete. Busca direto via db.session,
        sem passar por find_by_id, porque delete físico precisa
        conseguir achar até um registro já soft-deletado (ex.: limpeza
        definitiva por um job de retenção de dados)."""
        e = db.session.get(DoencaCronica, id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    def soft_delete(self, entity: DoencaCronica, motivo: str, observacoes_delete: Optional[str] = None) -> DoencaCronica:
        """Marca como removido em vez de apagar a linha. Não mexe em
        `status` -- o campo clínico (ativa/em-remissao) fica preservado
        intacto, só `deletado`/`deletado_em`/`motivo_delete`/
        `observacoes_delete` mudam. Idempotente: chamar de novo num
        registro já deletado só atualiza esses campos de novo (decisão
        deliberada -- ver observação no service sobre por que isso não
        levanta erro aqui)."""
        entity.deletado = True
        entity.deletado_em = datetime.now(timezone.utc)
        entity.motivo_delete = motivo
        entity.observacoes_delete = observacoes_delete
        db.session.add(entity)
        db.session.commit()
        return entity

    def restaurar(self, entity: DoencaCronica) -> DoencaCronica:
        """NOVO: reverte um soft delete, caso seja necessário reativar
        um registro removido por engano. Como `status` nunca foi
        alterado pelo soft delete, a restauração é direta -- o valor
        clínico anterior (ativa/em-remissao) volta junto, sem precisar
        de parâmetro adicional."""
        entity.deletado = False
        entity.deletado_em = None
        entity.motivo_delete = None
        entity.observacoes_delete = None
        db.session.add(entity)
        db.session.commit()
        return entity
    
    # --- F1: Doenças crônicas mais comuns na base ---
    def top_cid_ativas(self, id_empresa: int, limite: int = 10) -> list:
        """Ranking de codigo_cid10 com status='ativa', entre os pacientes
        da empresa. Não filtra por período -- é o estado atual da base,
        não um evento pontual. Filtra deletado == False explicitamente:
        diferente da tentativa anterior com "deletado" dentro do Enum
        de status, agora status e deletado são campos independentes,
        então uma doença soft-deletada que estava "ativa" continua
        batendo em status=='ativa' e precisa ser excluída à parte.

        Retorna: [{"codigo_cid10": "I10", "descricao_cid10": "Hipertensão", "total": 214}, ...]
        """
        linhas = (
            db.session.query(
                DoencaCronica.codigo_cid10.label("codigo"),
                DoencaCronica.descricao_cid10.label("descricao"),
                func.count(DoencaCronica.id).label("total"),
            )
            .join(Paciente, DoencaCronica.id_paciente == Paciente.id)
            .filter(Paciente.id_empresa == id_empresa)
            .filter(DoencaCronica.status == "ativa")
            .filter(DoencaCronica.deletado == False)
            .group_by(DoencaCronica.codigo_cid10, DoencaCronica.descricao_cid10)
            .order_by(func.count(DoencaCronica.id).desc())
            .limit(limite)
            .all()
        )
        return [
            {"codigo_cid10": linha.codigo, "descricao_cid10": linha.descricao, "total": linha.total}
            for linha in linhas
        ]