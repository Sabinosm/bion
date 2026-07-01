"""
Extensoes SQLAlchemy/Migrate compartilhadas por todos os modelos do Bion.

Mantido como Flask-SQLAlchemy (db.Model) porque toda a aplicacao usa esse
estilo nos repositories e nas migrations. Os modelos ficam divididos por
dominio em arquivos proprios (corp.py, usuarios.py, paciente.py,
catalogo.py, protocolos.py, clinico.py, auditoria.py) em vez de um unico
modelos.py monolitico -- esse .py original agora serve so de referencia
de schema, nao e mais importado por ninguem.

Os modelos sao importados no final deste arquivo (depois de `db` estar
definido) para: (1) evitar import circular, ja que cada modulo de modelo
faz `from src.database import db`; e (2) garantir que todas as classes
estejam registradas no metadata do SQLAlchemy antes de qualquer
`db.create_all()` ou migration ser executada.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

# Import tardio (depois de `db` existir) para registrar todos os modelos.
from src.database.corp import RegiaoGeografica, Empresa  # noqa: E402,F401
from src.database.usuarios import Usuario, Configuracao  # noqa: E402,F401
from src.database.paciente import (  # noqa: E402,F401
    Paciente, PacientePessoal, Alergia, DoencaCronica,
    MedicamentoEmUso, Consentimento,
)
from src.database.catalogo import (  # noqa: E402,F401
    CatalogoExames, CatalogoMedicamentos, InteracoesMedicamentos,
)
from src.database.protocolos import (  # noqa: E402,F401
    CatalogoFluxogramasMts, CatalogoModulos, OutputBion,
    ProtocoloCatalogo, ProtocoloMts, ProtocoloPersonalizado,
)
from src.database.clinico import (  # noqa: E402,F401
    Consulta, Atendimento, ColetaClinica, SinalVital, InputProtocolo,
    InputProtocoloExecucao, ResultadoPrescricao, Prescricao, PrescricaoExame,
)
from src.database.auditoria import LogAcesso, LogAlteracao  # noqa: E402,F401

__all__ = [
    "db", "migrate",
    "RegiaoGeografica", "Empresa",
    "Usuario", "Configuracao",
    "Paciente", "PacientePessoal", "Alergia", "DoencaCronica",
    "MedicamentoEmUso", "Consentimento",
    "CatalogoExames", "CatalogoMedicamentos", "InteracoesMedicamentos",
    "CatalogoFluxogramasMts", "CatalogoModulos", "OutputBion",
    "ProtocoloCatalogo", "ProtocoloMts", "ProtocoloPersonalizado",
    "Consulta", "Atendimento", "ColetaClinica", "SinalVital",
    "InputProtocolo", "InputProtocoloExecucao", "ResultadoPrescricao",
    "Prescricao", "PrescricaoExame",
    "LogAcesso", "LogAlteracao",
]
