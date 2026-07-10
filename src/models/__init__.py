

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()


# Auditoria
from src.models.auditoria import LogAcesso, LogAlteracao, StepUpToken

# Catálogo
from src.models.catalogos import (
    CatalogoExames,
    CatalogoMedicamentos,
    InteracoesMedicamentos,
    PrescricaoExame,
)

# Clínico
from src.models.clinico import (
    Atendimento,
    ColetaClinica,
    Consulta,
    InputProtocolo,
    InputProtocoloExecucao,
    Prescricao,
    ResultadoPrescricao,
    SinalVital,
)

# Corporativo
from src.models.corp import Empresa, RegiaoGeografica

# Paciente
from src.models.pacientes import (
    Alergia,
    Consentimento,
    DoencaCronica,
    MedicamentoEmUso,
    Paciente,
    PacientePessoal,
)

# Protocolo
from src.models.protocolos import (
    CatalogoFluxogramasMts,
    CatalogoModulos,
    OutputBion,
    ProtocoloCatalogo,
    ProtocoloMts,
    ProtocoloPersonalizado,
)

# Usuário
from src.models.usuarios import (
    Configuracao,
    ConfiguracaoProtocolo,
    CredencialWebAuthn,
    Usuario,
)

# ==============================================================================
# EXPOSIÇÃO DA API DO MÓDULO
# ==============================================================================

__all__ = [
    # Globais
    "db",
    "migrate",
    
    # Auditoria
    "LogAcesso",
    "LogAlteracao",
    "StepUpToken",
    
    # Catálogo
    "CatalogoExames",
    "CatalogoMedicamentos",
    "InteracoesMedicamentos",
    "PrescricaoExame",
    
    # Clínico
    "Atendimento",
    "ColetaClinica",
    "Consulta",
    "InputProtocolo",
    "InputProtocoloExecucao",
    "Prescricao",
    "ResultadoPrescricao",
    "SinalVital",
    
    # Corporativo
    "Empresa",
    "RegiaoGeografica",
    
    # Paciente
    "Alergia",
    "Consentimento",
    "DoencaCronica",
    "MedicamentoEmUso",
    "Paciente",
    "PacientePessoal",
    
    # Protocolo
    "CatalogoFluxogramasMts",
    "CatalogoModulos",
    "OutputBion",
    "ProtocoloCatalogo",
    "ProtocoloMts",
    "ProtocoloPersonalizado",
    
    # Usuário
    "Configuracao",
    "ConfiguracaoProtocolo",
    "CredencialWebAuthn",
    "Usuario",
]