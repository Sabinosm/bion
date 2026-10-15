"""Schemas Pydantic de ENTRADA do binário (Bloco 2).

Um schema por seção (usado pela rota granular) + `BinarioIn`, que compõe
os quatro (rota agregada). As 4 seções são OBRIGATÓRIAS no agregado, cada
uma com `possui` (obrigatório) e `nao_foi_possivel_coletar` (padrão False).

Regras (todas viram 422 via DadosInvalidosError no service):
  - nao_foi_possivel_coletar=true força possui=false; com itens -> erro.
  - possui=false com itens -> erro.
  - tipo sanguíneo não admite possui=false (todo paciente tem tipo
    sanguíneo; "desconhecido" é um valor registrável).
Os ITENS são dicts validados pelos schemas dos próprios dados clínicos
(AlergiaCreateSchema etc.) quando o service chama o service de cada dado:
uma só fonte de validação. O que depende do banco (possui=true sem item
e sem registro ativo; possui=false com registro ativo) fica no service.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SecaoBinario = Literal["alergias", "medicamentos", "tipo_sanguineo", "doenca_cronica"]


class _ConferenciaBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    possui: bool
    nao_foi_possivel_coletar: bool = False

    def _tem_conteudo(self) -> bool:
        return False

    @model_validator(mode="after")
    def _regras_do_binario(self):
        if self.nao_foi_possivel_coletar:
            if self._tem_conteudo():
                raise ValueError("nao_foi_possivel_coletar=true não aceita itens")
            self.possui = False
        elif not self.possui and self._tem_conteudo():
            raise ValueError("possui=false não aceita itens")
        return self


class _ConferenciaComItens(_ConferenciaBase):
    itens: list[dict] = Field(default_factory=list, max_length=50)

    def _tem_conteudo(self) -> bool:
        return bool(self.itens)


class BinarioAlergiasIn(_ConferenciaComItens):
    """itens: dicts no formato de AlergiaCreateSchema."""


class BinarioMedicamentosIn(_ConferenciaComItens):
    """itens: dicts no formato de MedicamentoEmUsoCreateSchema."""


class BinarioDoencaCronicaIn(_ConferenciaComItens):
    """itens: dicts no formato de DoencaCronicaCreateSchema."""


class BinarioTipoSanguineoIn(_ConferenciaBase):
    """possui=true com `tipo_sanguineo` registra uma nova observação (ou só
    confirma, se for igual ao vigente). Sem `tipo_sanguineo`, exige vigente."""
    tipo_sanguineo: Optional[str] = Field(default=None, max_length=20)

    def _tem_conteudo(self) -> bool:
        return self.tipo_sanguineo is not None

    @model_validator(mode="after")
    def _nao_admite_nega(self):
        if not self.possui and not self.nao_foi_possivel_coletar:
            raise ValueError(
                "tipo sanguíneo não admite possui=false: registre 'desconhecido' "
                "ou use nao_foi_possivel_coletar=true"
            )
        return self


class BinarioIn(BaseModel):
    """Corpo da rota agregada: as 4 seções, todas obrigatórias."""
    model_config = ConfigDict(extra="forbid")

    alergias: BinarioAlergiasIn
    medicamentos: BinarioMedicamentosIn
    tipo_sanguineo: BinarioTipoSanguineoIn
    doenca_cronica: BinarioDoencaCronicaIn


SCHEMA_POR_SECAO = {
    "alergias": BinarioAlergiasIn,
    "medicamentos": BinarioMedicamentosIn,
    "tipo_sanguineo": BinarioTipoSanguineoIn,
    "doenca_cronica": BinarioDoencaCronicaIn,
}