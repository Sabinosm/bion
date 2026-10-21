"""Casca do output: o que a IA preenche.

`OutputIA` = a PropostaPrescricaoIA que o projeto ja tem (conduta, por uuid do
catalogo) + o que a proposta nao cobre: se precisa de mais informacao, as
perguntas, a explicacao e os blocos do input usados. Assim:

    output.proposta  ->  PrescricaoIAService.registrar_proposta(...)  (inalterado)
    o resto          ->  perguntas ao profissional, explicacao, rastreabilidade

Fica de fora de proposito (o servidor decide, como no schema existente):
consistente_com_classificacao, status, formulado_por, origem e id_output.

Decisoes:
- extra="forbid": chave inventada pela IA e rejeitada.
- Todos os campos do envelope sao obrigatorios: a IA escreve [] em vez de esquecer.
- Texto livre so onde precisa, no idioma da Config.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from .proposta import PropostaPrescricaoIA, UuidStr

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Casca(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _em_branco_vira_none(v):
    return None if isinstance(v, str) and not v.strip() else v


class PerguntaPendente(_Casca):
    pergunta: Texto = Field(description="Pergunta objetiva a ser feita ao paciente ou ao profissional.")
    motivo: Texto = Field(description="Por que esta informacao muda a decisao.")
    bloco_relacionado: Texto | None = Field(
        description="Nome do bloco do input a que a lacuna se refere (ex.: 'alergias'). null se nao houver.")

    _a = field_validator("bloco_relacionado", mode="before")(_em_branco_vira_none)


class JustificativaMedicamento(_Casca):
    """Por que ESTE medicamento. O schema do projeto (MedicamentoPrescritoIn)
    proibe campos extras, entao a justificativa vai aqui, ligada pelo uuid."""
    uuid_catalogo: UuidStr = Field(description="uuid_catalogo de um medicamento de proposta.medicamentos.")
    justificativa: Texto = Field(description="Motivo clinico da escolha deste medicamento, citando dados do input.")


class OutputIA(_Casca):
    proposta: PropostaPrescricaoIA = Field(
        description="Conduta proposta, no formato do sistema. Referencie medicamentos e exames SOMENTE "
                    "pelo uuid do catalogo fornecido (uuid_catalogo / uuid_exame); nunca invente um uuid. "
                    "Se nada for recomendado: resultado=null, medicamentos=[] e exames=[]. "
                    "Com itens, 'resultado' (CID-10 e certeza; use 'suspeito' se for hipotese) e obrigatorio.")
    precisa_mais_informacao: bool = Field(
        description="true se faltam dados para decidir com seguranca. Pode ser true junto com uma proposta.")
    perguntas_pendentes: list[PerguntaPendente] = Field(
        description="O que perguntar. Vazia se precisa_mais_informacao for false; preenchida se for true.")
    justificativas_medicamentos: list[JustificativaMedicamento] = Field(
        description="Exatamente uma justificativa para cada item de proposta.medicamentos, ligada pelo "
                    "uuid_catalogo. Vazia se nao ha medicamentos.")
    detalhamento_explicacao: Texto = Field(
        description="Explicacao para o profissional, no idioma pedido em idioma_resposta, citando os dados do "
                    "input que sustentam a decisao e, se a conduta divergir do resultado do protocolo, por que.")
    blocos_considerados: list[Texto] = Field(
        min_length=1,
        description="Nomes dos blocos do input usados na decisao (ex.: ['alergias', 'protocolo']).")

    @model_validator(mode="after")
    def _coerencia(self):
        e = []
        if self.precisa_mais_informacao and not self.perguntas_pendentes:
            e.append("precisa_mais_informacao=true exige ao menos 1 item em perguntas_pendentes.")
        if not self.precisa_mais_informacao and self.perguntas_pendentes:
            e.append("perguntas_pendentes preenchida com precisa_mais_informacao=false: "
                     "ou ha pergunta pendente, ou nao precisa de mais informacao.")
        p = self.proposta
        tipo = p.resultado.tipo_prescricao if p.resultado else None
        if p.medicamentos and tipo != "farmacologica":
            e.append("proposta.medicamentos preenchido exige proposta.resultado.tipo_prescricao='farmacologica'.")
        if tipo == "farmacologica" and not p.medicamentos:
            e.append("tipo_prescricao='farmacologica' exige ao menos 1 item em proposta.medicamentos.")
        com = [m.uuid_catalogo for m in p.medicamentos]
        just = [j.uuid_catalogo for j in self.justificativas_medicamentos]
        if len(set(just)) != len(just):
            e.append("justificativas_medicamentos: uuid_catalogo repetido.")
        faltam = [u for u in com if u not in just]
        sobram = [u for u in just if u not in com]
        if faltam:
            e.append(f"justificativas_medicamentos: falta justificativa para {faltam}.")
        if sobram:
            e.append(f"justificativas_medicamentos: uuid fora de proposta.medicamentos: {sobram}.")
        if e:
            raise ValueError("\n".join(e))
        return self


def casca() -> dict:
    """JSON Schema do output, para entregar a IA como formato de resposta."""
    return OutputIA.model_json_schema()
