"""pdf_clinico.py -- leitura defensiva dos dados que os PDFs clínicos precisam.

Reúne o que atendimento, consulta e prescrição repetem: nome do paciente
(descriptografado), registro do profissional, identificadores/endereço da
empresa, moldura (cabeçalho/rodapé) e o CONTEXTO CLÍNICO DO PACIENTE NO MOMENTO
DO ATENDIMENTO.

POR QUE "NO MOMENTO": o PDF é remontado a cada pedido, sem guardar nada. Alergia,
doença crônica, medicamento em uso e tipo sanguíneo mudam depois (soft delete,
encerramento por revisão, nova observação). Se o PDF de um atendimento antigo
mostrasse o paciente de HOJE, ele deixaria de ser fiel ao que a equipe viu.
`contexto_clinico_em(paciente, t)` filtra pelos carimbos que o banco já guarda
(criado_em, deletado_em, encerrado_em, data_registro).

LIMITE CONHECIDO: MedicamentoEmUso não tem `criado_em`. Para ele, "nasceu em" =
início do atendimento de origem (id_atendimento_origem); sem origem (linha
anterior ao Bloco 2) conta como existente. "Parou em" usa `ate` quando o
registro foi encerrado.

Tudo aqui lê atributos com `attr()`, que aceita vários nomes e devolve None se
nenhum existir: se um campo tiver outro nome no seu model, o PDF mostra "-" em
vez de quebrar, e o ajuste é uma linha.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional

from src.core.security import aes_decrypt
from .pdf_base import Moldura, como_tz, como_utc, emitido_em_texto

AVISO_LGPD_INTERNO = (
    "Contém dados pessoais sensíveis de saúde (LGPD, Lei 13.709/2018). Uso restrito à finalidade "
    "assistencial, de auditoria ou de estudo. Não repasse nem armazene fora do prontuário."
)

AVISO_RESUMO = (
    "Resumo informativo gerado a partir do registro clínico. Não substitui prescrição, atestado, "
    "laudo ou orientação do profissional que o atendeu."
)


# ------------------------------------------------------------------ acessores
def attr(obj: Any, *nomes: str, default=None):
    """Primeiro atributo existente e não-None entre `nomes`."""
    if obj is None:
        return default
    for n in nomes:
        v = getattr(obj, n, None)
        if v is not None:
            return v
    return default


def tz_empresa(empresa):
    """ZoneInfo da empresa (Empresa.fuso_horario aceita nome ou ZoneInfo); padrão Brasília."""
    return como_tz(attr(empresa, "fuso_horario"))


def nome_paciente(paciente) -> str:
    """Nome descriptografado, ou o motivo de não haver nome (mesmas flags do bloco_paciente)."""
    if paciente is None:
        return "Paciente não informado"
    if getattr(paciente, "nao_identificado", False):
        return "Paciente não identificado"
    pessoal = getattr(paciente, "pessoal", None)
    if pessoal is None:
        return "Paciente anonimizado"
    return aes_decrypt(pessoal.nome_completo) or "Paciente sem nome"


def cpf_paciente(paciente) -> Optional[str]:
    pessoal = getattr(paciente, "pessoal", None)
    return pessoal.cpf_plaintext() if pessoal else None


def sexo_texto(sexo: Optional[str]) -> str:
    return {"M": "Masculino", "F": "Feminino", "I": "Indeterminado"}.get(sexo or "", "-")


def registro_profissional(usuario) -> Optional[str]:
    """'CRM 12345/MG' a partir de Usuario.atributos_profissionais_json (dict ou string JSON).

    AJUSTE se os nomes das chaves forem outros: só a tupla _CHAVES abaixo."""
    bruto = attr(usuario, "atributos_profissionais_json")
    if isinstance(bruto, str):
        try:
            bruto = json.loads(bruto)
        except ValueError:
            bruto = None
    if not isinstance(bruto, dict):
        return None
    uf = bruto.get("uf") or bruto.get("uf_registro") or bruto.get("uf_conselho")
    for chave, rotulo in _CHAVES:
        numero = bruto.get(chave)
        if numero:
            return f"{rotulo} {numero}" + (f"/{uf}" if uf else "")
    return None


_CHAVES = (("crm", "CRM"), ("coren", "COREN"), ("numero_registro", "Registro"),
           ("registro_profissional", "Registro"), ("registro", "Registro"))


def funcao_texto(usuario) -> str:
    return {"medico": "Médico", "enfermeiro": "Enfermeiro"}.get(
        attr(usuario, "funcao_clinica") or "", "Profissional")


def nome_usuario_por_id(id_usuario: Optional[int]) -> Optional[str]:
    """Nome de quem está GERANDO o documento (vem da sessão, só o id).
    SQL direto para não depender de onde o model Usuario mora; usuarios.nome_completo não é cifrado."""
    if not id_usuario:
        return None
    from src.models import db
    return db.session.execute(
        db.text("SELECT nome_completo FROM usuarios WHERE id_usuario = :i"), {"i": id_usuario}
    ).scalar()


def identificadores_empresa(empresa) -> str:
    partes = []
    if attr(empresa, "cnpj"):
        partes.append(f"CNPJ {empresa.cnpj}")
    if attr(empresa, "cnes"):
        partes.append(f"CNES {empresa.cnes}")
    return " · ".join(partes)


def endereco_empresa(empresa) -> str:
    """Só o que o model da Empresa tem (não há logradouro): bairro, número, CEP, cidade/UF."""
    reg = attr(empresa, "regiao_geografica")
    cidade = attr(reg, "municipio", "nome_municipio", "cidade", "nome")
    uf = attr(reg, "uf")
    local = f"{cidade}/{uf}" if cidade and uf else (cidade or uf)
    partes = [attr(empresa, "bairro"),
              f"nº {empresa.numero}" if attr(empresa, "numero") else None,
              attr(empresa, "complemento"),
              f"CEP {empresa.cep}" if attr(empresa, "cep") else None,
              local]
    return ", ".join(p for p in partes if p)


def cidade_uf_empresa(empresa) -> str:
    reg = attr(empresa, "regiao_geografica")
    cidade = attr(reg, "municipio", "nome_municipio", "cidade", "nome")
    uf = attr(reg, "uf")
    return f"{cidade}/{uf}" if cidade and uf else (cidade or uf or "")


def moldura(empresa, titulo: str, agora: datetime, emitido_por: Optional[str], aviso: str,
            marca: Optional[str] = None, extra: Optional[List[str]] = None) -> Moldura:
    """Cabeçalho/rodapé padrão. `agora` e o fuso da empresa dão o 'dia da semana, data e hora'."""
    return Moldura(
        empresa_nome=attr(empresa, "nome_fantasia", "razao_social", default="Instituição"),
        empresa_linha=" · ".join(p for p in [identificadores_empresa(empresa), endereco_empresa(empresa)] if p),
        titulo=titulo,
        emitido_em=emitido_em_texto(agora, tz_empresa(empresa)),
        emitido_por=emitido_por,
        aviso_rodape=aviso,
        marca_dagua=marca,
        extra_rodape=extra or [],
    )


# ---------------------------------------------------- contexto clínico no tempo
@dataclass
class ContextoClinico:
    """Fotografia do que valia em `t`. Dicts simples: os renderizadores não tocam no ORM."""
    alergias: List[dict] = field(default_factory=list)
    medicamentos: List[dict] = field(default_factory=list)
    doencas: List[dict] = field(default_factory=list)
    tipo_sanguineo: Optional[dict] = None


_ORDEM_GRAVIDADE = {"grave": 0, "moderada": 1, "leve": 2, None: 3}


def _vigente(criado_em, deletado, deletado_em, t, encerrado_em=None) -> bool:
    c = como_utc(criado_em)
    if c is not None and c > t:
        return False
    if deletado:
        d = como_utc(deletado_em)
        if d is None or d <= t:        # removido antes de t (ou sem data: tratado como removido)
            return False
    if encerrado_em is not None and como_utc(encerrado_em) <= t:
        return False
    return True


def contexto_clinico_em(paciente, t: datetime) -> ContextoClinico:
    """Alergias, medicamentos, doenças crônicas e tipo sanguíneo vigentes em `t` (aware, UTC)."""
    t = como_utc(t)
    ctx = ContextoClinico()
    if paciente is None:
        return ctx

    for a in getattr(paciente, "alergias", None) or []:
        if not _vigente(a.criado_em, a.deletado, a.deletado_em, t):
            continue
        reacoes = [r for r in (a.reacoes or []) if _vigente(r.criado_em, r.deletado, r.deletado_em, t)]
        graves = sorted((r.gravidade for r in reacoes), key=lambda g: _ORDEM_GRAVIDADE.get(g, 3))
        ctx.alergias.append({
            "substancia": a.substancia,
            "gravidade": graves[0] if graves else None,      # a MAIOR entre as reações vigentes
            "reacoes": [(r.manifestacao, r.gravidade, r.descricao) for r in reacoes],
            "confirmado": bool(a.flag_confirmado),
        })
    ctx.alergias.sort(key=lambda x: _ORDEM_GRAVIDADE.get(x["gravidade"], 3))

    for m in getattr(paciente, "medicamentos_em_uso", None) or []:
        origem = attr(m, "atendimento_origem")
        nasceu = attr(origem, "data_hora_inicio")
        if not _vigente(nasceu, m.deletado, m.deletado_em, t):
            continue
        if m.status_uso != "ativo":
            # encerrado: ainda valia em t só se terminou depois dele
            if not (m.ate and m.ate > t.date()):
                continue
        ctx.medicamentos.append({"descricao": m.descricao, "dose": m.dose, "frequencia": m.frequencia,
                                 "desde": m.desde, "ate": m.ate})

    for d in getattr(paciente, "doencas", None) or []:
        if _vigente(d.criado_em, d.deletado, d.deletado_em, t, d.encerrado_em):
            ctx.doencas.append({"codigo": d.codigo_cid10, "descricao": d.descricao_cid10,
                                "status": d.status, "desde": d.desde, "observacoes": d.observacoes})

    obs = [o for o in (getattr(paciente, "observacoes_tipo_sanguineo", None) or [])
           if como_utc(o.data_registro) <= t]
    if obs:
        mais_recente = max(obs, key=lambda o: (como_utc(o.data_registro), o.id))
        ctx.tipo_sanguineo = {"valor": mais_recente.tipo_sanguineo, "registrado_em": mais_recente.data_registro}
    return ctx
