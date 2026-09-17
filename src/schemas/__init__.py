from .schema_alergia import (
    AlergiaCreateSchema,
    AlergiaAtualizarSchema,
    AlergiaRemoverSchema,
    ReacaoAlergiaCreateSchema,
)
from .schema_config import (
    ConfiguracoesSchema,
    DesignSchema,
    PreferenciasSchema,
    validar_configuracoes,
)
from .schema_consentimento import (
    ConsentimentoCreateSchema,
    ConsentimentoDispensaEmergenciaSchema,
    ConsentimentoRevogarSchema,
)
from .schema_doenca_cronica import (
    DoencaCronicaCreateSchema,
    DoencaCronicaAtualizarSchema,
    DoencaCronicaRemoverSchema,
)
from .schema_empresa import (
    CadastroEmpresaSchema,
    AtualizacaoEmpresaSchema,
)
from .schema_medicamento_em_uso import (
    MedicamentoEmUsoCreateSchema,
    MedicamentoEmUsoAtualizarSchema,
    MedicamentoEmUsoRemoverSchema,
)
from .schema_paciente import (
    PacienteAtualizarPessoalSchema,
    PacienteAtualizarClinicoSchema,
    PacienteCriarSchema,
)
from .schema_tipo_sanguineo import (
    TipoSanguineoCreateSchema,
)

__all__ = [
    # schema_alergia
    "AlergiaCreateSchema",
    "AlergiaAtualizarSchema",
    "AlergiaRemoverSchema",
    "ReacaoAlergiaCreateSchema",
    # schema_config
    "ConfiguracoesSchema",
    "DesignSchema",
    "PreferenciasSchema",
    "validar_configuracoes",
    # schema_consentimento
    "ConsentimentoCreateSchema",
    "ConsentimentoDispensaEmergenciaSchema",
    "ConsentimentoRevogarSchema",
    # schema_doenca_cronica
    "DoencaCronicaCreateSchema",
    "DoencaCronicaAtualizarSchema",
    "DoencaCronicaRemoverSchema",
    # schema_empresa
    "CadastroEmpresaSchema",
    "AtualizacaoEmpresaSchema",
    # schema_medicamento_em_uso
    "MedicamentoEmUsoCreateSchema",
    "MedicamentoEmUsoAtualizarSchema",
    "MedicamentoEmUsoRemoverSchema",
    # schema_paciente
    "PacienteAtualizarPessoalSchema",
    "PacienteAtualizarClinicoSchema",
    "PacienteCriarSchema",
    # schema_tipo_sanguineo
    "TipoSanguineoCreateSchema",
]