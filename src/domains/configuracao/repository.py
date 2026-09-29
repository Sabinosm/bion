from typing import Optional, List

from sqlalchemy.exc import IntegrityError

from src.models import db
from src.core.interfaces import IRepository
from src.models.usuarios import Configuracao, ConfiguracaoProtocolo
from src.models.corp import EmpresaProtocolo
from src.core.exceptions import ConflictoError


class ConfiguracaoRepository(IRepository[Configuracao]):

    def find_by_id(self, id: int) -> Optional[Configuracao]:
        return db.session.get(Configuracao, id)

    def find_by_uuid(self, uuid: str) -> Optional[Configuracao]:
        return Configuracao.query.filter_by(uuid=uuid).first()

    def find_by_usuario(self, id_usuario: int) -> Optional[Configuracao]:
        return Configuracao.query.filter_by(id_usuario=id_usuario).first()

    def save(self, entity: Configuracao) -> Configuracao:
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

    def find_all(self) -> List[Configuracao]:
        return Configuracao.query.all()

    # --- ConfiguracaoProtocolo (linhas filhas: preferência pessoal por protocolo) ---

    def find_protocolos_by_configuracao(self, id_configuracao: int) -> List[ConfiguracaoProtocolo]:
        return ConfiguracaoProtocolo.query.filter_by(id_configuracao=id_configuracao).all()

    def find_protocolo(self, id_configuracao: int, id_protocolo: int) -> Optional[ConfiguracaoProtocolo]:
        return ConfiguracaoProtocolo.query.filter_by(
            id_configuracao=id_configuracao, id_protocolo=id_protocolo
        ).first()

    def find_default_do_escopo(self, id_configuracao: int, escopo: str) -> Optional[ConfiguracaoProtocolo]:
        """Localiza o protocolo atualmente marcado como default pessoal de um escopo,
        necessário para 'liberar o slot' antes de definir um novo default
        (a UNIQUE KEY uq_default_por_escopo não permite dois defaults no mesmo escopo)."""
        return ConfiguracaoProtocolo.query.filter_by(
            id_configuracao=id_configuracao, escopo_default=escopo
        ).first()

    def save_protocolo(self, entity: ConfiguracaoProtocolo, commit: bool = True) -> ConfiguracaoProtocolo:
        """commit=False só faz flush: permite trocar o default de escopo
        (liberar o anterior + ocupar o novo) na MESMA transação.

        Duplo clique/requests concorrentes podem violar uq_config_protocolo
        ou uq_default_por_escopo -- vira ConflictoError (409) em vez de 500."""
        db.session.add(entity)
        try:
            if commit:
                db.session.commit()
            else:
                db.session.flush()
        except IntegrityError:
            db.session.rollback()
            raise ConflictoError("Operação simultânea detectada. Tente novamente.")
        return entity

    def find_vinculos_ativos_da_empresa(self, id_empresa: int) -> List[EmpresaProtocolo]:
        """Protocolos liberados (ativo=True) para a empresa -- base do catálogo
        efetivo e do fallback institucional do default."""
        return EmpresaProtocolo.query.filter_by(id_empresa=id_empresa, ativo=True).all()