"""
Dominio Catalogo (exames) -- conteudo de apoio (MedlinePlus).

Guardado para a IA (e para consulta futura): o aplicativo NUNCA chama o MedlinePlus
durante o atendimento. Escrito apenas por SincronizarConteudoExamesService.
"""

from sqlalchemy.dialects.mysql import MEDIUMTEXT

from src.models import db
from src.models.types import BigIntPK


class CatalogoExamesConteudo(db.Model):
    __tablename__ = "catalogo_exames_conteudo"
    __table_args__ = (
        db.UniqueConstraint("id_catalogo_exame", "idioma", "fonte", "url_hash",
                            name="uq_conteudo_exame_fonte_url"),
        db.Index("ix_conteudo_exame", "id_catalogo_exame", "idioma"),
    )

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    id_catalogo_exame = db.Column(
        db.BigInteger, db.ForeignKey("catalogo_exames.id_catalogo_exame", ondelete="CASCADE"), nullable=False)
    idioma = db.Column(db.String(5), nullable=False)          # 'en', 'es'
    fonte = db.Column(db.String(30), nullable=False)          # 'medlineplus'
    tipo = db.Column(db.String(10), nullable=False)           # 'exame' | 'topico'
    titulo = db.Column(db.String(255))
    url = db.Column(db.String(500))
    url_hash = db.Column(db.String(40), nullable=False)
    outros_nomes_json = db.Column(db.JSON)
    secoes_json = db.Column(db.JSON)                          # [{chave, titulo, texto}]
    texto_plano = db.Column(db.Text().with_variant(MEDIUMTEXT, "mysql"))
    atribuicao = db.Column(db.String(255))
    codigo_loinc_consultado = db.Column(db.String(10))
    hash_conteudo = db.Column(db.String(64))
    buscado_em = db.Column(db.DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return f"<CatalogoExamesConteudo exame={self.id_catalogo_exame} {self.idioma} {self.tipo} [{self.titulo}]>"


class CatalogoExamesConteudoConsulta(db.Model):
    """Resultado da ultima tentativa de busca por (exame, idioma, fonte): ok, sem_conteudo ou erro."""
    __tablename__ = "catalogo_exames_conteudo_consulta"
    __table_args__ = (
        db.UniqueConstraint("id_catalogo_exame", "idioma", "fonte", name="uq_consulta_exame_fonte"),
    )

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    id_catalogo_exame = db.Column(
        db.BigInteger, db.ForeignKey("catalogo_exames.id_catalogo_exame", ondelete="CASCADE"), nullable=False)
    idioma = db.Column(db.String(5), nullable=False)
    fonte = db.Column(db.String(30), nullable=False)
    codigo_loinc = db.Column(db.String(10))
    status = db.Column(db.String(15), nullable=False)
    http_status = db.Column(db.SmallInteger)
    mensagem = db.Column(db.String(255))
    consultado_em = db.Column(db.DateTime(timezone=True), nullable=False)
