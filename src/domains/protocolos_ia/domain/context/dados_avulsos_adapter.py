"""Este arquivo constrói o ContextoClinicoSeguro a partir de dados enviados no corpo da requisição (consulta avulsa).

Itens malformados são rejeitados com o nome do campo e a posição. Nenhum item clínico é descartado em silêncio.
Chaves extras dentro de um item (ids, uuids, flags internas) são ignoradas e nunca saem daqui.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from src.core.exceptions import DadosInvalidosError

from .clinical_context import (
    SEXO_NAO_INFORMADO,
    SEXOS,
    AlergiaSegura,
    ContextoClinicoSeguro,
    DoencaCronicaSegura,
    MedicamentoEmUsoSeguro,
    SecaoClinica,
    SinalVitalSeguro,
    faixa_etaria_por_data,
)
from .sanitizer import texto_opcional
from .triage_adapter import de_resultado_deterministico

SECOES_NEGAVEIS = ("alergias", "doencas", "medicamentos")
_TIPO_SINAL = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_CID10 = re.compile(r"^[A-Z]\d{2}(\.\d{1,2})?$")
_TIPO_SANGUINEO = re.compile(r"^(A|B|AB|O)[+-]$")
FLAG_REJEITADO = "fora-limite-rejeitado"
FLAG_ALERTADO = "fora-limite-alertado"
IDADE_MAXIMA_ANOS = 130


def _erro(campo: str, mensagem: str) -> DadosInvalidosError:
    return DadosInvalidosError(f"{campo}: {mensagem}", campo=campo)


def _itens(valor: Any, campo: str) -> list[dict]:
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise _erro(campo, "deve ser uma lista.")
    for posicao, item in enumerate(valor):
        if not isinstance(item, dict):
            raise _erro(campo, f"item {posicao} deve ser um objeto.")
    return valor


def _numero(valor: Any, campo: str, posicao: int) -> float:
    if isinstance(valor, bool):
        raise _erro(campo, f"item {posicao} possui valor numérico inválido.")
    try:
        numero = float(Decimal(str(valor)))
    except (InvalidOperation, ValueError, TypeError):
        raise _erro(campo, f"item {posicao} possui valor numérico inválido.") from None
    if not math.isfinite(numero):
        raise _erro(campo, f"item {posicao} possui valor numérico inválido.")
    return numero


def _data(valor: Any, hoje: date) -> Optional[date]:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        nascimento = valor.date()
    elif isinstance(valor, date):
        nascimento = valor
    elif isinstance(valor, str):
        try:
            nascimento = date.fromisoformat(valor.strip())
        except ValueError:
            raise _erro("data_nascimento", "use o formato AAAA-MM-DD.") from None
    else:
        raise _erro("data_nascimento", "use o formato AAAA-MM-DD.")
    if nascimento > hoje:
        raise _erro("data_nascimento", "não pode ser futura.")
    if hoje.year - nascimento.year > IDADE_MAXIMA_ANOS:
        raise _erro("data_nascimento", "fora do intervalo plausível.")
    return nascimento


def _sinais(valor: Any) -> tuple[SinalVitalSeguro, ...]:
    saida = []
    for i, sv in enumerate(_itens(valor, "sinais_vitais")):
        tipo = sv.get("tipo_parametro")
        if not isinstance(tipo, str) or not _TIPO_SINAL.match(tipo):
            raise _erro("sinais_vitais", f"item {i} sem tipo_parametro válido.")
        if sv.get("valor_numerico") is None:
            raise _erro("sinais_vitais", f"item {i} sem valor_numerico.")
        if sv.get("flag_validacao_faixa") == FLAG_REJEITADO:
            continue
        saida.append(
            SinalVitalSeguro(
                tipo=tipo,
                valor=_numero(sv["valor_numerico"], "sinais_vitais", i),
                unidade=texto_opcional(sv.get("unidade"), 20) or "",
                alerta_fora_do_limite=sv.get("flag_validacao_faixa") == FLAG_ALERTADO,
            )
        )
    return tuple(saida)


def _alergias(valor: Any) -> tuple[AlergiaSegura, ...]:
    saida = []
    for i, a in enumerate(_itens(valor, "alergias")):
        substancia = texto_opcional(a.get("substancia") or a.get("nome_substancia"), 200)
        if not substancia:
            raise _erro("alergias", f"item {i} sem substância.")
        saida.append(
            AlergiaSegura(
                substancia=substancia,
                tipo=texto_opcional(a.get("tipo_alergia") or a.get("tipo"), 50),
                gravidade=texto_opcional(a.get("gravidade") or a.get("gravidade_maxima"), 30),
            )
        )
    return tuple(saida)


def _doencas(valor: Any) -> tuple[DoencaCronicaSegura, ...]:
    saida = []
    for i, d in enumerate(_itens(valor, "doencas")):
        descricao = texto_opcional(d.get("descricao_cid10") or d.get("descricao") or d.get("nome_doenca"), 300)
        if not descricao:
            raise _erro("doencas", f"item {i} sem descrição.")
        cid = d.get("codigo_cid10") or d.get("cid10")
        if cid is not None and not (isinstance(cid, str) and _CID10.match(cid)):
            raise _erro("doencas", f"item {i} com código CID-10 inválido.")
        saida.append(DoencaCronicaSegura(descricao=descricao, codigo_cid10=cid, status=texto_opcional(d.get("status"), 30)))
    return tuple(saida)


def _medicamentos(valor: Any) -> tuple[MedicamentoEmUsoSeguro, ...]:
    saida = []
    for i, m in enumerate(_itens(valor, "medicamentos")):
        nome = texto_opcional(
            m.get("principio_ativo") or m.get("nome_principio_ativo") or m.get("descricao") or m.get("nome"), 200
        )
        if not nome:
            raise _erro("medicamentos", f"item {i} sem princípio ativo ou descrição.")
        saida.append(
            MedicamentoEmUsoSeguro(
                principio_ativo=nome,
                dose=texto_opcional(m.get("dose"), 100),
                frequencia=texto_opcional(m.get("frequencia"), 100),
            )
        )
    return tuple(saida)


def contexto_de_dados_avulsos(
    *,
    sexo_biologico: Optional[str] = None,
    data_nascimento: Any = None,
    sinais_vitais: Any = None,
    alergias: Any = None,
    doencas: Any = None,
    medicamentos: Any = None,
    queixa_principal: Optional[str] = None,
    resultado_triagem: Any = None,
    tipo_sanguineo: Optional[str] = None,
    secoes_negadas: Iterable[str] = (),
    hoje: Optional[date] = None,
) -> ContextoClinicoSeguro:
    """Esta função valida e normaliza os dados avulsos e devolve o contexto seguro.

    Lista ausente ou vazia vira nao_informado. Só uma negativa explícita em secoes_negadas vira paciente_nega.
    """
    hoje = hoje or date.today()
    if sexo_biologico is None:
        sexo = SEXO_NAO_INFORMADO
    elif sexo_biologico in SEXOS:
        sexo = SEXOS[sexo_biologico]
    else:
        raise _erro("sexo_biologico", "valores aceitos: M, F, I.")

    if tipo_sanguineo is not None and not (isinstance(tipo_sanguineo, str) and _TIPO_SANGUINEO.match(tipo_sanguineo)):
        raise _erro("tipo_sanguineo", "valor inválido.")

    negadas = set(secoes_negadas)
    invalidas = negadas - set(SECOES_NEGAVEIS)
    if invalidas:
        raise _erro("secoes_negadas", f"valores aceitos: {', '.join(SECOES_NEGAVEIS)}.")

    sinais = _sinais(sinais_vitais)
    return ContextoClinicoSeguro(
        sexo=sexo,
        faixa_etaria=faixa_etaria_por_data(_data(data_nascimento, hoje), hoje),
        tipo_sanguineo=tipo_sanguineo,
        sinais_vitais=SecaoClinica.de_itens(sinais),
        alergias=SecaoClinica.de_itens(_alergias(alergias), "alergias" in negadas),
        doencas_cronicas=SecaoClinica.de_itens(_doencas(doencas), "doencas" in negadas),
        medicamentos_em_uso=SecaoClinica.de_itens(_medicamentos(medicamentos), "medicamentos" in negadas),
        queixa_principal=texto_opcional(queixa_principal, 500),
        resultado_triagem=de_resultado_deterministico(resultado_triagem),
    )
