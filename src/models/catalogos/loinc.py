"""
Dominio Catalogo (exames) -- referencia LOINC.

Tabelas SOMENTE-LEITURA para a aplicacao: sao carregadas dos arquivos da
distribuicao do LOINC (Loinc.csv, linguistic variant pt-BR, PanelsAndForms.csv)
pelo CarregarLoincService. O catalogo que o medico usa e o CatalogoExames
(curado); ele aponta para um LoincTermo por codigo_loinc.
"""

from src.models import db


class LoincTermo(db.Model):
    __tablename__ = "loinc_termo"
    __table_args__ = (
        db.Index("ix_loinc_termo_escopo", "classtype", "status"),
        db.Index("ix_loinc_termo_rank_pedido", "rank_pedido"),
    )

    loinc_num = db.Column(db.String(10), primary_key=True)
    componente = db.Column(db.String(255))
    propriedade = db.Column(db.String(255))
    tempo = db.Column(db.String(255))
    sistema = db.Column(db.String(255))
    escala = db.Column(db.String(255))
    metodo = db.Column(db.String(255))
    classe = db.Column(db.String(255))
    classtype = db.Column(db.SmallInteger)
    status = db.Column(db.String(20))
    order_obs = db.Column(db.String(15))
    panel_type = db.Column(db.String(50))
    nome_longo = db.Column(db.String(255))
    nome_exibicao = db.Column(db.String(255))
    nome_curto = db.Column(db.String(255))
    unidade_exemplo_ucum = db.Column(db.String(255))
    rank_teste = db.Column(db.Integer)
    rank_pedido = db.Column(db.Integer)
    versao_loinc = db.Column(db.String(20))

    traducoes = db.relationship("LoincTermoTraducao", back_populates="termo")

    def __repr__(self):
        return f"<LoincTermo {self.loinc_num} [{self.nome_exibicao}]>"


class LoincTermoTraducao(db.Model):
    """Partes do nome traduzidas (linguistic variant). NAO e nome de exibicao:
    no pt-BR o LONG_COMMON_NAME vem vazio e as partes misturam siglas em ingles."""
    __tablename__ = "loinc_termo_traducao"

    loinc_num = db.Column(db.String(10), db.ForeignKey("loinc_termo.loinc_num"), primary_key=True)
    idioma = db.Column(db.String(10), primary_key=True)
    componente = db.Column(db.String(255))
    propriedade = db.Column(db.String(255))
    tempo = db.Column(db.String(255))
    sistema = db.Column(db.String(255))
    escala = db.Column(db.String(255))
    metodo = db.Column(db.String(255))
    nome_curto = db.Column(db.String(255))
    nomes_relacionados = db.Column(db.Text)

    termo = db.relationship("LoincTermo", back_populates="traducoes")


class LoincPainelItem(db.Model):
    """Resultados que compoem um painel laboratorial (ex.: itens do hemograma)."""
    __tablename__ = "loinc_painel_item"
    __table_args__ = (db.Index("ix_loinc_painel_item_painel", "painel_loinc", "sequencia"),)

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True, autoincrement=True)
    painel_loinc = db.Column(db.String(10), db.ForeignKey("loinc_termo.loinc_num"), nullable=False)
    filho_loinc = db.Column(db.String(10), db.ForeignKey("loinc_termo.loinc_num"), nullable=False)
    sequencia = db.Column(db.Integer)
    obrigatoriedade = db.Column(db.String(20))

    painel = db.relationship("LoincTermo", foreign_keys=[painel_loinc])
    filho = db.relationship("LoincTermo", foreign_keys=[filho_loinc])
