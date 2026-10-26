"""Este arquivo converte o snapshot congelado do InputModel do host (OutputBion.input_ia_json) em ContextoClinicoSeguro.

Campos estruturados de identificação não devem entrar no contexto clínico; texto livre vindo de queixas ou resultados pode conter identificadores. Aqui o snapshot é lido por whitelist, os estados
(informado, paciente_nega, nao_informado) são preservados e todo texto livre passa pelo sanitizador.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..exceptions import SnapshotInvalidoError
from .clinical_context import (
    SEXO_NAO_INFORMADO,
    AlergiaSegura,
    ContextoClinicoSeguro,
    DoencaCronicaSegura,
    MedicamentoEmUsoSeguro,
    ProtocoloExecutadoSeguro,
    SecaoClinica,
    SinalVitalSeguro,
    faixa_etaria_por_idade,
)
from .sanitizer import limpar_estrutura, texto_opcional

_IDIOMA = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
_SEXOS_SNAPSHOT = {"masculino", "feminino", "indeterminado"}
LIMITE_RESULTADO_PROTOCOLO = 6000


def _dict(valor: Any) -> dict:
    return valor if isinstance(valor, dict) else {}


def _lista(valor: Any) -> list:
    return valor if isinstance(valor, list) else []


def _numero(valor: Any) -> Optional[float]:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def _secao(bloco: Any, construir) -> SecaoClinica:
    """Itens reais viram informado. Sem itens, o status gravado pelo host decide entre paciente_nega e nao_informado."""
    bloco = _dict(bloco)
    itens = tuple(x for x in (construir(i) for i in _lista(bloco.get("itens")) if isinstance(i, dict)) if x is not None)
    if itens:
        return SecaoClinica("informado", itens)
    if bloco.get("status") == "paciente_nega":
        return SecaoClinica("paciente_nega")
    return SecaoClinica("nao_informado")


def _alergia(i: dict) -> Optional[AlergiaSegura]:
    substancia = texto_opcional(i.get("substancia"), 200)
    if not substancia:
        return None
    reacoes = []
    for r in _lista(i.get("reacoes")):
        r = _dict(r)
        partes = [texto_opcional(r.get(k), 200) for k in ("manifestacao", "gravidade", "descricao")]
        texto = " | ".join(p for p in partes if p)
        if texto:
            reacoes.append(texto)
    return AlergiaSegura(
        substancia=substancia,
        gravidade=texto_opcional(i.get("gravidade_maxima"), 30),
        reacoes=tuple(reacoes[:10]),
    )


def _doenca(i: dict) -> Optional[DoencaCronicaSegura]:
    descricao = texto_opcional(i.get("descricao"), 300)
    if not descricao:
        return None
    return DoencaCronicaSegura(
        descricao=descricao,
        codigo_cid10=texto_opcional(i.get("cid10"), 10),
        status=texto_opcional(i.get("status"), 30),
    )


def _medicamento(i: dict) -> Optional[MedicamentoEmUsoSeguro]:
    nome = texto_opcional(i.get("principio_ativo") or i.get("descricao"), 200)
    if not nome:
        return None
    verificavel = i.get("interacoes_verificaveis")
    return MedicamentoEmUsoSeguro(
        principio_ativo=nome,
        dose=texto_opcional(i.get("dose"), 100),
        frequencia=texto_opcional(i.get("frequencia"), 100),
        interacoes_verificaveis=verificavel if isinstance(verificavel, bool) else None,
    )


def _sinais(bloco: Any) -> SecaoClinica:
    medicoes = _dict(_dict(bloco).get("medicoes"))
    itens = []
    for tipo, m in medicoes.items():
        m = _dict(m)
        valor = _numero(m.get("valor"))
        if valor is None or not isinstance(tipo, str):
            continue
        itens.append(
            SinalVitalSeguro(
                tipo=texto_opcional(tipo, 40) or "desconhecido",
                valor=valor,
                unidade=texto_opcional(m.get("unidade"), 20) or "",
                alerta_fora_do_limite=m.get("alerta") == "fora_do_limite",
            )
        )
    return SecaoClinica("informado", tuple(itens)) if itens else SecaoClinica("nao_informado")


def _tipo_sanguineo(bloco: Any) -> Optional[str]:
    for item in _lista(_dict(bloco).get("itens")):
        tipo = texto_opcional(_dict(item).get("tipo"), 5)
        if tipo:
            return tipo
    return None


def _resultado_protocolo(resultado: Any) -> Optional[dict]:
    if not isinstance(resultado, dict) or not resultado:
        return None
    limpo = limpar_estrutura(resultado)
    if len(json.dumps(limpo, ensure_ascii=False)) <= LIMITE_RESULTADO_PROTOCOLO:
        return limpo
    reduzido = {k: limpo[k] for k in ("classificacao",) if k in limpo}
    return reduzido or None


def _protocolos(bloco: Any) -> tuple[ProtocoloExecutadoSeguro, ...]:
    saida = []
    for item in _lista(_dict(bloco).get("itens")):
        for e in _lista(_dict(item).get("execucoes")):
            e = _dict(e)
            if e.get("status") == "cancelada":
                continue
            ausentes = tuple(x for x in (texto_opcional(a, 200) for a in _lista(e.get("dados_ausentes"))) if x)
            saida.append(
                ProtocoloExecutadoSeguro(
                    protocolo=texto_opcional(e.get("protocolo"), 120),
                    sigla=texto_opcional(e.get("sigla"), 20),
                    status=texto_opcional(e.get("status"), 30),
                    dados_ausentes=ausentes[:20],
                    resultado=_resultado_protocolo(e.get("resultado_deterministico")),
                )
            )
    return tuple(saida)


def _queixa(bloco: Any) -> tuple[Optional[str], Optional[str]]:
    bloco = _dict(bloco)
    bruta = bloco.get("queixa_principal")
    if isinstance(bruta, list):
        bruta = "; ".join(str(x) for x in bruta[:5])
    return texto_opcional(bruta, 500), texto_opcional(bloco.get("avpu"), 30)


def contexto_de_snapshot(snapshot: Any) -> ContextoClinicoSeguro:
    """Esta função monta o contexto seguro a partir do dict congelado em OutputBion.input_ia_json."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("contexto"), dict):
        raise SnapshotInvalidoError()
    ctx = snapshot["contexto"]
    paciente = _dict(ctx.get("paciente"))
    anos = paciente.get("idade_anos")
    meses = paciente.get("idade_meses")
    anos = anos if isinstance(anos, int) and not isinstance(anos, bool) and 0 <= anos <= 130 else None
    meses = meses if isinstance(meses, int) and not isinstance(meses, bool) and meses >= 0 else None
    sexo = paciente.get("sexo") if paciente.get("sexo") in _SEXOS_SNAPSHOT else SEXO_NAO_INFORMADO

    queixa, avpu = _queixa(ctx.get("queixa"))
    observacoes = texto_opcional(_dict(ctx.get("atendimento")).get("observacoes_profissional"), 1000)
    coletas = _lista(_dict(ctx.get("coleta_clinica")).get("coletas"))
    sintomas = _numero(_dict(coletas[-1]).get("desde_quando_sintomas_horas")) if coletas else None
    idioma = snapshot.get("idioma_resposta")
    lacunas = tuple(x for x in (texto_opcional(f, 200) for f in _lista(snapshot.get("faltando"))[:50]) if x)

    return ContextoClinicoSeguro(
        sexo=sexo,
        faixa_etaria=faixa_etaria_por_idade(anos, meses),
        peso_kg=_numero(paciente.get("peso_kg")),
        altura_cm=_numero(paciente.get("altura_cm")),
        tipo_sanguineo=_tipo_sanguineo(ctx.get("tipo_sanguineo")),
        sinais_vitais=_sinais(ctx.get("sinais_vitais")),
        alergias=_secao(ctx.get("alergias"), _alergia),
        doencas_cronicas=_secao(ctx.get("doenca_cronica"), _doenca),
        medicamentos_em_uso=_secao(ctx.get("medicamentos"), _medicamento),
        queixa_principal=queixa,
        avpu=avpu,
        observacoes_atendimento=observacoes,
        sintomas_ha_horas=sintomas,
        protocolos_executados=_protocolos(ctx.get("protocolo")),
        lacunas=lacunas,
        idioma_resposta=idioma if isinstance(idioma, str) and _IDIOMA.match(idioma) else "pt-BR",
    )
