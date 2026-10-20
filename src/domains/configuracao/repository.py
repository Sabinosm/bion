"""
repository.py

Acesso a dados do domínio Configuração: a configuração de cada usuário
(preferências de aparência e idioma), as linhas filhas com a preferência
pessoal por protocolo e a consulta aos protocolos liberados pela empresa, que
limitam o que o usuário pode habilitar.

A persistência da configuração confirma a transação a cada gravação. A das
linhas de protocolo também, a menos que quem chama peça só o flush: isso
permite trocar o protocolo padrão de um escopo (liberar o anterior e ocupar o
novo) numa mesma transação.
"""

from typing import Optional, List, Tuple

from sqlalchemy.exc import IntegrityError

from src.models import db
from src.core.interfaces import IRepository
from src.models.usuarios import Configuracao, ConfiguracaoProtocolo
from src.domains.empresa.empresa_protocolo.empresa_protocolo_repository import EmpresaProtocoloRepository
from src.core.exceptions import ConflictoError
from src.models.corp import EmpresaProtocolo

_repo_empresa_protocolo = EmpresaProtocoloRepository()

class ConfiguracaoRepository(IRepository[Configuracao]):

    # ------------------------------------------------------------------
    # Configuracao
    # ------------------------------------------------------------------

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

    def criar_com_favoritos(
        self, entity: Configuracao, ids_protocolos: List[int]
    ) -> Tuple[Configuracao, bool]:
        """Cria a configuração e seus favoritos iniciais numa única transação (tudo ou nada).

        Se outra requisição criou a configuração do mesmo usuário antes
        (violação de unicidade), desfaz esta tentativa e devolve a que já
        existe, sem erro: quem chega depois simplesmente a usa.

        Args:
            entity: configuração nova, ainda não gravada.
            ids_protocolos: protocolos do catálogo a gravar como favoritos (em_uso=True).

        Returns:
            (configuracao, criada): `criada` é False quando a configuração já
            existia por causa da disputa com outra requisição.

        Raises:
            IntegrityError: se a violação não vier de uma configuração já
                existente (ex.: usuário inexistente).
        """
        db.session.add(entity)
        try:
            db.session.flush()  # obtém o id da configuração antes de criar as linhas filhas
            for id_protocolo in ids_protocolos:
                db.session.add(ConfiguracaoProtocolo(
                    id_configuracao=entity.id, id_protocolo=id_protocolo, em_uso=True,
                ))
            db.session.commit()
            return entity, True
        except IntegrityError:
            db.session.rollback()
            existente = self.find_by_usuario(entity.id_usuario)
            if existente is None:
                raise
            return existente, False

    def delete(self, id: int) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        db.session.commit()
        return True

    # ------------------------------------------------------------------
    # ConfiguracaoProtocolo (preferência pessoal por protocolo)
    # ------------------------------------------------------------------

    def find_protocolos_by_configuracao(self, id_configuracao: int) -> List[ConfiguracaoProtocolo]:
        return ConfiguracaoProtocolo.query.filter_by(id_configuracao=id_configuracao).all()

    def find_protocolo(self, id_configuracao: int, id_protocolo: int) -> Optional[ConfiguracaoProtocolo]:
        """Linha de preferência de um protocolo específico, ou None se o usuário nunca o configurou."""
        return ConfiguracaoProtocolo.query.filter_by(
            id_configuracao=id_configuracao, id_protocolo=id_protocolo
        ).first()

    def find_default_do_escopo(self, id_configuracao: int, escopo: str) -> Optional[ConfiguracaoProtocolo]:
        """Protocolo atualmente marcado como padrão pessoal de um escopo.

        Necessário para liberar o slot antes de definir um novo padrão: a
        UNIQUE KEY uq_default_por_escopo não permite dois padrões no mesmo
        escopo.
        """
        return ConfiguracaoProtocolo.query.filter_by(
            id_configuracao=id_configuracao, escopo_default=escopo
        ).first()

    def save_protocolo(self, entity: ConfiguracaoProtocolo, commit: bool = True) -> ConfiguracaoProtocolo:
        """Grava uma linha de preferência de protocolo.

        Com `commit=False` só faz flush, para a troca do padrão de um escopo
        (liberar o anterior e ocupar o novo) sair na MESMA transação.

        Cliques duplos ou requisições concorrentes podem violar
        uq_config_protocolo ou uq_default_por_escopo; isso vira ConflictoError
        (409) em vez de erro 500.
        """
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

    # ------------------------------------------------------------------
    # EmpresaProtocolo (liberação institucional)
    # ------------------------------------------------------------------

    def find_empresa_protocolo(self, id_empresa: int, id_protocolo: int) -> Optional[EmpresaProtocolo]:
        """Vínculo entre a empresa e um protocolo do catálogo, ativo ou não, ou None se nunca foi vinculado."""
        return _repo_empresa_protocolo.find_empresa_com_catatlogo(id_empresa=id_empresa, id_protocolo_catalogo=id_protocolo)

    def find_vinculos_ativos_da_empresa(self, id_empresa: int) -> List[EmpresaProtocolo]:
        """Protocolos liberados (ativo=True) para a empresa.

        Base do catálogo efetivo e do fallback institucional do padrão.
        """
        return _repo_empresa_protocolo.find_ativos_por_empresa(id_empresa=id_empresa)
