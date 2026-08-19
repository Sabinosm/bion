

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()


# Auditoria
from src.models.auditoria import LogAcesso, LogAlteracao, StepUpToken, StepUpReautenticacao

# Catálogo
from src.models.catalogos import (
    CatalogoExames,
    CatalogoMedicamentos,
    InteracoesMedicamentos,

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
    PrescricaoExame,
)

# Corporativo
from src.models.corp import Empresa, RegiaoGeografica, EmpresaIdentificador, TipoJurisdicao

# Paciente
from src.models.pacientes import (
    Alergia,
    ReacaoAlergia,
    ObservacaoTipoSanguineo,
    Consentimento,
    DoencaCronica,
    MedicamentoEmUso,
    Paciente,
    PacienteDadosPessoais,
    
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
    "StepUpReautenticacao",
    
    # Catálogo
    "CatalogoExames",
    "CatalogoMedicamentos",
    "InteracoesMedicamentos",
    
    
    # Clínico
    "Atendimento",
    "ColetaClinica",
    "Consulta",
    "InputProtocolo",
    "InputProtocoloExecucao",
    "Prescricao",
    "ResultadoPrescricao",
    "SinalVital",
    "LoincSinalVital",
    "PrescricaoExame",
    
    # Corporativo
    "Empresa",
    "RegiaoGeografica",
    "EmpresaIdentificicador",
    "TipoJurisdicao",
    
    # Paciente
    "Alergia",
    "Consentimento",
    "DoencaCronica",
    "MedicamentoEmUso",
    "Paciente",
    "PacientePessoal",
    "ObservacaoTipoSanguineo",
    "ReacaoAlergia",
    
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
    "PapelProfissional",
]