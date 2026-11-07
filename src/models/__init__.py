from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()


from src.models.auditoria import LogAcesso, LogAlteracao, StepUpToken, StepUpReautenticacao

from src.models.catalogos import (
    CatalogoExames,
    CatalogoMedicamentos,
    InteracoesMedicamentos,
    Contraindicacao,
    LogSincronizacaoCatalogo,
    IndicacaoTerapeutica,
    LoincPainelItem,
    LoincTermo,
    LoincTermoTraducao,
    CatalogoExamesConteudo,
)

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
    CondutaEnfermagem,
    LoincSinalVital,
    Binario,
)

from src.models.corp import (
    Empresa,
    RegiaoGeografica,
    EmpresaIdentificador,
    TipoJurisdicao,
    EmpresaProtocolo,
)

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

from src.models.protocolos import (
    CatalogoFluxogramasMts,
    CatalogoModulos,
    ModuloVersao,
    ModuloVersaoCampo,
    OutputBion,
    ProtocoloCatalogo,
    ProtocoloComposicao,
    ProtocoloComposicaoConfig,
    ProtocoloEscoreConfig,
    ProtocoloMts,
    ProtocoloVersao,
    VariavelClinica,
)

from src.models.usuarios import (
    Configuracao,
    ConfiguracaoProtocolo,
    CredencialWebAuthn,
    Usuario,
    CredencialTOTP,
    PapelProfissional,
)

__all__ = [
    "db",
    "migrate",
    "LogAcesso",
    "LogAlteracao",
    "StepUpToken",
    "StepUpReautenticacao",
    "CatalogoExames",
    "CatalogoMedicamentos",
    "InteracoesMedicamentos",
    "Contraindicacao",
    "LogSincronizacaoCatalogo",
    "IndicacaoTerapeutica",
    "LoincPainelItem",
    "LoincTermo",
    "LoincTermoTraducao",
    "CatalogoExamesConteudo",
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
    "CondutaEnfermagem",
    "Binario",
    "Empresa",
    "RegiaoGeografica",
    "EmpresaIdentificador",
    "TipoJurisdicao",
    "EmpresaProtocolo",
    "Alergia",
    "Consentimento",
    "DoencaCronica",
    "MedicamentoEmUso",
    "Paciente",
    "PacienteDadosPessoais",
    "ObservacaoTipoSanguineo",
    "ReacaoAlergia",
    "CatalogoFluxogramasMts",
    "CatalogoModulos",
    "ModuloVersao",
    "ModuloVersaoCampo",
    "OutputBion",
    "ProtocoloCatalogo",
    "ProtocoloComposicao",
    "ProtocoloComposicaoConfig",
    "ProtocoloEscoreConfig",
    "ProtocoloMts",
    "ProtocoloVersao",
    "VariavelClinica",
    "Configuracao",
    "ConfiguracaoProtocolo",
    "CredencialWebAuthn",
    "Usuario",
    "PapelProfissional",
    "CredencialTOTP",
]
