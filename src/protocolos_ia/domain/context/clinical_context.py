"""Este arquivo define o ContextoClinicoSeguro: a única forma de dado clínico que pode chegar à LLM.

Cada seção de lista carrega um estado explícito (informado, paciente_nega, nao_informado) para que
ausência de coleta nunca seja confundida com ausência de condição clínica.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Generic, Literal, Optional, Tuple, TypeVar

from ..exceptions import SerializacaoContextoError

Estado = Literal["informado", "paciente_nega", "nao_informado"]
T = TypeVar("T")

SEXOS = {"M": "masculino", "F": "feminino", "I": "indeterminado"}
SEXO_NAO_INFORMADO = "nao_informado"
FAIXA_NAO_INFORMADA = "nao_informado"


@dataclass(frozen=True)
class SinalVitalSeguro:
    tipo: str
    valor: float
    unidade: str
    alerta_fora_do_limite: bool = False

    def para_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"tipo": self.tipo, "valor": self.valor, "unidade": self.unidade}
        if self.alerta_fora_do_limite:
            d["alerta"] = "fora_do_limite"
        return d


@dataclass(frozen=True)
class AlergiaSegura:
    substancia: str
    tipo: Optional[str] = None
    gravidade: Optional[str] = None
    reacoes: Tuple[str, ...] = ()

    def para_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"substancia": self.substancia}
        if self.tipo:
            d["tipo"] = self.tipo
        if self.gravidade:
            d["gravidade"] = self.gravidade
        if self.reacoes:
            d["reacoes"] = list(self.reacoes)
        return d


@dataclass(frozen=True)
class DoencaCronicaSegura:
    descricao: str
    codigo_cid10: Optional[str] = None
    status: Optional[str] = None

    def para_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"descricao": self.descricao}
        if self.codigo_cid10:
            d["cid10"] = self.codigo_cid10
        if self.status:
            d["status"] = self.status
        return d


@dataclass(frozen=True)
class MedicamentoEmUsoSeguro:
    principio_ativo: str
    dose: Optional[str] = None
    frequencia: Optional[str] = None
    interacoes_verificaveis: Optional[bool] = None

    def para_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"principio_ativo": self.principio_ativo}
        if self.dose:
            d["dose"] = self.dose
        if self.frequencia:
            d["frequencia"] = self.frequencia
        if self.interacoes_verificaveis is not None:
            d["interacoes_verificaveis"] = self.interacoes_verificaveis
        return d


@dataclass(frozen=True)
class ResultadoTriagemSeguro:
    """Resultado achatado de um protocolo determinístico de triagem (MTS ou NEWS2)."""

    protocolo: Optional[str] = None
    versao_protocolo: Optional[str] = None
    cor_mts: Optional[str] = None
    tempo_max_espera_minutos: Optional[int] = None
    discriminante_determinante: Optional[str] = None
    score_news2: Optional[int] = None
    nivel_risco_news2: Optional[str] = None
    alertas: Tuple[str, ...] = ()

    def para_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"alertas": list(self.alertas)}
        if self.protocolo:
            d["protocolo"] = self.protocolo
        if self.versao_protocolo:
            d["versao"] = self.versao_protocolo
        if self.cor_mts:
            d["cor_mts"] = self.cor_mts
            d["tempo_max_espera_min"] = self.tempo_max_espera_minutos
            d["discriminante"] = self.discriminante_determinante
        if self.score_news2 is not None:
            d["score_news2"] = self.score_news2
            d["nivel_risco"] = self.nivel_risco_news2
        return d


@dataclass(frozen=True)
class ProtocoloExecutadoSeguro:
    """Execução de protocolo vinda do snapshot do atendimento. O resultado já passou pelo sanitizador."""

    protocolo: Optional[str]
    sigla: Optional[str]
    status: Optional[str]
    dados_ausentes: Tuple[str, ...] = ()
    resultado: Optional[Dict[str, Any]] = None

    def para_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        for chave, valor in (("protocolo", self.protocolo), ("sigla", self.sigla), ("status", self.status)):
            if valor:
                d[chave] = valor
        if self.dados_ausentes:
            d["dados_ausentes"] = list(self.dados_ausentes)
        if self.resultado:
            d["resultado_deterministico"] = self.resultado
        return d


@dataclass(frozen=True)
class SecaoClinica(Generic[T]):
    estado: Estado = "nao_informado"
    itens: Tuple[T, ...] = ()

    def para_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"estado": self.estado}
        if self.estado == "informado":
            d["itens"] = [i.para_dict() for i in self.itens]
        return d

    @classmethod
    def de_itens(cls, itens: Tuple[T, ...], negada: bool = False) -> "SecaoClinica[T]":
        """Itens reais sempre vencem a negativa. Sem itens, vale a negativa explícita ou nao_informado."""
        if itens:
            return cls("informado", itens)
        return cls("paciente_nega" if negada else "nao_informado", ())


@dataclass(frozen=True)
class ContextoClinicoSeguro:
    sexo: str = SEXO_NAO_INFORMADO
    faixa_etaria: str = FAIXA_NAO_INFORMADA
    peso_kg: Optional[float] = None
    altura_cm: Optional[float] = None
    tipo_sanguineo: Optional[str] = None
    sinais_vitais: SecaoClinica[SinalVitalSeguro] = field(default_factory=SecaoClinica)
    alergias: SecaoClinica[AlergiaSegura] = field(default_factory=SecaoClinica)
    doencas_cronicas: SecaoClinica[DoencaCronicaSegura] = field(default_factory=SecaoClinica)
    medicamentos_em_uso: SecaoClinica[MedicamentoEmUsoSeguro] = field(default_factory=SecaoClinica)
    queixa_principal: Optional[str] = None
    avpu: Optional[str] = None
    observacoes_atendimento: Optional[str] = None
    sintomas_ha_horas: Optional[float] = None
    resultado_triagem: Optional[ResultadoTriagemSeguro] = None
    protocolos_executados: Tuple[ProtocoloExecutadoSeguro, ...] = ()
    lacunas: Tuple[str, ...] = ()
    idioma_resposta: str = "pt-BR"

    def possui_resultado_protocolo(self) -> bool:
        return self.resultado_triagem is not None or bool(self.protocolos_executados)

    def possui_conteudo_clinico(self) -> bool:
        """Verdadeiro quando há ao menos um dado clínico real para analisar."""
        return bool(
            self.queixa_principal
            or self.sinais_vitais.itens
            or self.alergias.itens
            or self.doencas_cronicas.itens
            or self.medicamentos_em_uso.itens
            or self.possui_resultado_protocolo()
            or self.observacoes_atendimento
        )

    def serializar(self) -> Dict[str, Any]:
        """Único ponto de saída de dados para a LLM. Constrói campo a campo e confirma a serialização JSON."""
        try:
            paciente: Dict[str, Any] = {"sexo": self.sexo, "faixa_etaria": self.faixa_etaria}
            if self.peso_kg is not None:
                paciente["peso_kg"] = self.peso_kg
            if self.altura_cm is not None:
                paciente["altura_cm"] = self.altura_cm
            if self.tipo_sanguineo:
                paciente["tipo_sanguineo"] = self.tipo_sanguineo
            saida: Dict[str, Any] = {
                "idioma_resposta": self.idioma_resposta,
                "paciente": paciente,
                "sinais_vitais": self.sinais_vitais.para_dict(),
                "alergias": self.alergias.para_dict(),
                "doencas_cronicas": self.doencas_cronicas.para_dict(),
                "medicamentos_em_uso": self.medicamentos_em_uso.para_dict(),
            }
            if self.queixa_principal:
                saida["queixa_principal"] = self.queixa_principal
            if self.avpu:
                saida["avpu"] = self.avpu
            if self.observacoes_atendimento:
                saida["observacoes_atendimento"] = self.observacoes_atendimento
            if self.sintomas_ha_horas is not None:
                saida["sintomas_ha_horas"] = self.sintomas_ha_horas
            if self.resultado_triagem:
                saida["resultado_triagem"] = self.resultado_triagem.para_dict()
            if self.protocolos_executados:
                saida["protocolos_executados"] = [p.para_dict() for p in self.protocolos_executados]
            if self.lacunas:
                saida["lacunas"] = list(self.lacunas)
            json.dumps(saida, ensure_ascii=False)
            return saida
        except (TypeError, ValueError) as exc:
            raise SerializacaoContextoError() from exc


def serializar_para_prompt(contexto: ContextoClinicoSeguro) -> str:
    """Esta função devolve o JSON do contexto com os caracteres < e > escapados, para que o dado não feche o delimitador do prompt."""
    texto = json.dumps(contexto.serializar(), ensure_ascii=False, indent=2)
    return texto.replace("<", "\\u003c").replace(">", "\\u003e")


def faixa_etaria_por_data(nascimento: Optional[date], hoje: Optional[date] = None) -> str:
    """Esta função converte data de nascimento em faixa etária. Datas futuras são rejeitadas por quem chama."""
    if nascimento is None:
        return FAIXA_NAO_INFORMADA
    hoje = hoje or date.today()
    anos = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
    dias = (hoje - nascimento).days
    if dias < 28:
        return "neonato (0-27 dias)"
    return _faixa(anos, lactente_ate_2_anos=True)


def faixa_etaria_por_idade(anos: Optional[int], meses: Optional[int] = None) -> str:
    """Esta função converte idade em anos (e meses, quando menor de 2 anos) em faixa etária."""
    if anos is None:
        return FAIXA_NAO_INFORMADA
    if anos < 2 and meses is not None and meses < 1:
        return "neonato ou lactente (menos de 1 mês)"
    return _faixa(anos, lactente_ate_2_anos=True)


def _faixa(anos: int, lactente_ate_2_anos: bool) -> str:
    if anos < 2 and lactente_ate_2_anos:
        return "lactente (28 dias a 23 meses)"
    if anos < 6:
        return "pré-escolar (2-5 anos)"
    if anos < 12:
        return "escolar (6-11 anos)"
    if anos < 18:
        return "adolescente (12-17 anos)"
    if anos < 30:
        return "adulto jovem (18-29 anos)"
    if anos < 40:
        return "adulto 30-39 anos"
    if anos < 50:
        return "adulto 40-49 anos"
    if anos < 60:
        return "adulto 50-59 anos"
    if anos < 80:
        return "idoso (60-79 anos)"
    return "idoso avançado (80+ anos)"
