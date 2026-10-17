"""
Serviço de assinatura digital LGPD — fluxo QR code presencial.

Este service só ORQUESTRA a sessão (token, validação, arquivos). A criação do
Consentimento é delegada ao ConsentimentoService.ativar_novo, para que a regra
"um consentimento ativo por paciente" seja única.
"""

from datetime import datetime, timezone, timedelta
import base64
import binascii
import hashlib
import hmac
import logging
import os
import re

from pydantic import ValidationError

from src.core.exceptions import (
    RecursoNaoEncontradoError,
    DadosInvalidosError,
    ConflictoError,
)
from src.models.pacientes import ConsentimentoSessaoAssinatura
from src.domains.paciente.repositories import (
    PacienteRepository,
    ConsentimentoRepository,
    ConsentimentoSessaoAssinaturaRepository,
)
from src.domains.paciente.schemas.schema_consentimento import erros_pydantic_por_campo
from src.domains.paciente.schemas.schema_consentimento_digital import (
    GerarLinkAssinaturaSchema,
    AssinaturaDigitalSchema,
    ESCOPOS_VALIDOS,
    AuditoriaAssinaturaSchema,
    EscopoDigitalSchema,
    ConsentimentoDigitalCreateSchema,
)
from .consentimento_service import ConsentimentoService
from ..termos.termo_renderer import gerar_termo, gerar_pdf_bytes, versao_vigente
from ..termos.consentimento_pdf import montar_pdf_assinado, formatar_cpf, sha256_bytes
from src.domains.empresa.repository import EmpresaRepository 
from src.core.security import aes_decrypt

logger = logging.getLogger(__name__)


def _janela_copia_minutos() -> int:
    """Quanto tempo, depois de assinar, o paciente pode baixar a própria cópia com o token."""
    return int(os.getenv("CONSENT_JANELA_COPIA_MIN", "15"))
_formatar_cpf = formatar_cpf


def _mascarar_cpf(cpf) -> str:
    """***.456.789-** -- a rota publica (token) mostra o suficiente para o
    titular reconhecer o proprio CPF, sem expor o numero completo."""
    d = re.sub(r"\D", "", cpf or "")
    return f"***.{d[3:6]}.{d[6:9]}-**" if len(d) == 11 else "-"


class ConsentimentoDigitalService:

    TEMPO_EXPIRACAO_MINUTOS = 5
    TAMANHO_MAX_ASSINATURA = 1 * 1024 * 1024   # 1 MB já decodificado
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

    def __init__(self):
        self.paciente_repo = PacienteRepository()
        self.empresa_repo = EmpresaRepository()
        self.consentimento_repo = ConsentimentoRepository()
        self.sessao_repo = ConsentimentoSessaoAssinaturaRepository()
        self.consentimento_svc = ConsentimentoService()

    # ------------------------------------------------------------------ helpers
    def _paciente_ou_404(self, uuid_paciente: str, id_empresa: int):
        p = self.paciente_repo.find_by_uuid(uuid_paciente, id_empresa)
        if not p:
            raise RecursoNaoEncontradoError(f"Paciente não encontrado: {uuid_paciente}")
        return p

    @staticmethod
    def _identificacao(paciente) -> tuple:
        """(nome, cpf) em texto claro. Paciente NAO tem .nome/.cpf: a PII
        fica cifrada em paciente.pessoal. Sem dados pessoais (emergencia
        nao identificada, ou anonimizado) nao ha quem assine o termo --
        nesses casos o caminho e a dispensa por emergencia."""
        pessoal = paciente.pessoal
        if not pessoal:
            raise DadosInvalidosError(
                "Paciente sem dados pessoais (nao identificado ou anonimizado): "
                "identifique-o antes de coletar o termo, ou registre a dispensa por emergencia."
            )
        return aes_decrypt(pessoal.nome_completo), aes_decrypt(pessoal.cpf)

    @staticmethod
    def _expirado(sessao) -> bool:
        """MySQL costuma devolver datetime naive; assume UTC (como gravamos)."""
        exp = sessao.expira_em
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp

    def _checar_sessao_utilizavel(self, sessao, msg_usado: str, msg_expirado: str):
        if sessao.status == "usado":
            raise ConflictoError(msg_usado)
        if sessao.status == "expirado" or self._expirado(sessao):
            if sessao.status != "expirado":
                sessao.status = "expirado"
                self.sessao_repo.save(sessao, commit=True)
            raise DadosInvalidosError(msg_expirado)

    # ------------------------------------------------------------ gerar link
    def gerar_link_assinatura(
        self,
        uuid_paciente: str,
        id_medico: int,
        id_empresa: int,
        versao_termo: str = None,
        ip_medico: str = None,
    ) -> dict:
        """Texto e PDF do termo são MONTADOS aqui (template da versão + dados da
        empresa da sessão). O cliente só escolhe a versão: não envia caminho,
        texto nem unidade (id_unidade == id_empresa da sessão)."""
        try:
            entrada = GerarLinkAssinaturaSchema(versao_termo=versao_termo)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))
        versao = entrada.versao_termo or versao_vigente()

        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        nome, cpf = self._identificacao(p)   # falha cedo, antes de expirar links anteriores
        empresa = self.empresa_repo.find_by_id(id_empresa)
        if not empresa:
            raise RecursoNaoEncontradoError("Empresa não encontrada.")
        texto_termo, _pdf_termo, hash_pdf = gerar_termo(versao, empresa, ESCOPOS_VALIDOS)
        agora = datetime.now(timezone.utc)

        # um link pendente por paciente: gerar novo cancela os anteriores
        self.sessao_repo.expirar_pendentes_do_paciente(p.id)

        sessao = ConsentimentoSessaoAssinatura(
            token=ConsentimentoSessaoAssinatura.gerar_token(),
            id_paciente=p.id,
            id_unidade=id_empresa,
            id_medico_gerador=id_medico,
            hash_pdf_original=hash_pdf,
            texto_termo_snapshot=texto_termo,
            versao_termo=versao, 
            criado_em=agora,
            expira_em=agora + timedelta(minutes=self.TEMPO_EXPIRACAO_MINUTOS),
            ip_geracao=ip_medico,
        )
        self.sessao_repo.save(sessao, commit=True)

        return {
            "token": sessao.token,
            "url_assinatura": f"/v1/api/pacientes/lgpd/assinar/{sessao.token}",
            "expira_em": sessao.expira_em.isoformat(),
            "paciente_nome": nome,
            "paciente_cpf": _formatar_cpf(cpf),
        }

    # ------------------------------------------------- rota pública (GET)
    def obter_dados_sessao(self, token: str) -> dict:
        sessao = self.sessao_repo.find_by_token(token)
        if not sessao:
            raise RecursoNaoEncontradoError("Link de assinatura inválido.")
        self._checar_sessao_utilizavel(
            sessao,
            "Este link já foi utilizado para assinatura.",
            "Link de assinatura expirado. Solicite um novo ao médico.",
        )
        nome, cpf = self._identificacao(sessao.paciente)
        return {
            "token": sessao.token,
            "paciente_nome": nome,
            "paciente_cpf": _mascarar_cpf(cpf),
            "escopos_disponiveis": [
                {"codigo": k, "descricao": d} for k, d in ESCOPOS_VALIDOS.items()
            ],
            "versao_termo": sessao.versao_termo,
            "texto_termo": sessao.texto_termo_snapshot,
            "hash_pdf_original": sessao.hash_pdf_original,
            "termo_pdf_url": f"/v1/api/pacientes/lgpd/assinar/{sessao.token}/termo.pdf",
            "expira_em": sessao.expira_em.isoformat(),
            "unidade_id": sessao.id_unidade,
        }

    def obter_termo_pdf(self, token: str) -> tuple:
        """PDF do termo para o paciente baixar (rota pública, o token é a autenticação).
        Refeito em memória do texto da sessão; nada é lido nem gravado em disco.
        Retorna (bytes, sha256). Mesmas regras de validade do GET: só link pendente."""
        sessao = self.sessao_repo.find_by_token(token)
        if not sessao:
            raise RecursoNaoEncontradoError("Link de assinatura inválido.")
        self._checar_sessao_utilizavel(
            sessao,
            "Este link já foi utilizado para assinatura.",
            "Link de assinatura expirado. Solicite um novo ao médico.",
        )
        pdf = gerar_pdf_bytes(sessao.texto_termo_snapshot)
        return pdf, sha256_bytes(pdf)

    def obter_copia_assinada(self, token: str) -> bytes:
        """Cópia do PDF assinado para o PRÓPRIO paciente (rota pública, token = autenticação).
        Só com link 'usado' e dentro da janela após a assinatura (CONSENT_JANELA_COPIA_MIN,
        padrão 15 min). Refeito em memória; nada em disco. Todo caso inválido responde 404
        igual, para o token não revelar em que estado está."""
        negado = RecursoNaoEncontradoError("Cópia indisponível.")
        sessao = self.sessao_repo.find_by_token(token)
        if not sessao or sessao.status != "usado" or sessao.usado_em is None or not sessao.consentimento:
            raise negado
        usado = sessao.usado_em
        if usado.tzinfo is None:           # MySQL devolve naive; gravamos em UTC
            usado = usado.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > usado + timedelta(minutes=_janela_copia_minutos()):
            raise RecursoNaoEncontradoError(
                "O prazo para baixar a cópia terminou. Peça uma cópia à clínica."
            )
        if not sessao.consentimento.assinatura_png:
            raise negado
        pdf, _ = self._refazer_pdf(sessao.consentimento)
        return pdf

    # ------------------------------------------------ rota pública (POST)
    def _validar_payload(self, dados: dict, hash_esperado: str):
        """Formato via AssinaturaDigitalSchema; aqui só o que depende de estado
        (hash == o da sessão) e a decodificação segura do PNG."""
        try:
            entrada = AssinaturaDigitalSchema(**dados)
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        if not hmac.compare_digest(entrada.hash_pdf_original, hash_esperado):
            raise DadosInvalidosError(
                "Hash do documento não confere. O termo pode ter sido alterado. "
                "Recarregue a página e tente novamente."
            )

        try:
            img = base64.b64decode(entrada.assinatura_canvas.split(",", 1)[-1], validate=True)
        except (binascii.Error, ValueError):
            raise DadosInvalidosError("Formato da assinatura inválido.")
        if len(img) > self.TAMANHO_MAX_ASSINATURA or not img.startswith(self.PNG_MAGIC):
            raise DadosInvalidosError("A assinatura deve ser uma imagem PNG válida.")

        return entrada, img

    def registrar_assinatura(
        self,
        token: str,
        dados_front: dict,
        ip_paciente: str = None,
        user_agent_servidor: str = None,
    ) -> dict:
        # Trava a linha da sessão: um segundo POST simultâneo espera aqui e
        # depois enxerga status='usado'.
        sessao = self.sessao_repo.find_by_token(token, for_update=True)
        if not sessao:
            raise RecursoNaoEncontradoError("Token inválido.")
        self._checar_sessao_utilizavel(sessao, "Assinatura já registrada para este link.", "Link expirado.")

        entrada, img_bytes = self._validar_payload(dados_front, sessao.hash_pdf_original)
        ip_paciente = (ip_paciente or "")[:45] or None   # coluna String(45)

        # user-agent confiável vem do header; o do front é só fallback
        escopos = entrada.escopos_selecionados
        user_agent = (user_agent_servidor or entrada.user_agent or "")[:500]
        geo = entrada.geolocalizacao or ""
        geo_divergente = entrada.geo_divergente

        # sem microssegundos: o MySQL (DATETIME sem fração) arredonda; o que é impresso no
        # PDF tem de ser exatamente o que é gravado, para o PDF poder ser refeito depois.
        agora = datetime.now(timezone.utc).replace(microsecond=0)

        try:
            nome, cpf = self._identificacao(sessao.paciente)
            pdf_final = montar_pdf_assinado(
                texto_termo=sessao.texto_termo_snapshot,
                hash_pdf_original=sessao.hash_pdf_original,
                nome=nome, cpf=cpf, versao_termo=sessao.versao_termo,
                data=agora, ip=ip_paciente, user_agent=user_agent, geo=geo,
                assinatura_png=img_bytes,
                escopos_aceitos=escopos, escopos_oferecidos=list(ESCOPOS_VALIDOS),
            )
            hash_pdf_final = sha256_bytes(pdf_final)   # o PDF em si NÃO é guardado

            registro = ConsentimentoDigitalCreateSchema(
                versao_termo=sessao.versao_termo,
                hash_documento=hash_pdf_final,
                escopo_consentimento=EscopoDigitalSchema(
                    escopo=escopos,
                    escopos_oferecidos=list(ESCOPOS_VALIDOS),
                    audit=AuditoriaAssinaturaSchema(
                        id_sessao=sessao.id,
                        ip=ip_paciente,
                        user_agent=user_agent,
                        geolocalizacao=geo,
                        geo_divergente=geo_divergente,
                        texto_integral_aceito=sessao.texto_termo_snapshot,
                        hash_pdf_original=sessao.hash_pdf_original,
                        hash_pdf_final=hash_pdf_final,
                    ),
                ),
            )

            consentimento = self.consentimento_svc.ativar_novo(
                sessao.id_paciente,
                coletado_por=sessao.id_medico_gerador,
                versao_termo=registro.versao_termo,
                canal_coleta=registro.canal_coleta,
                escopo=registro.escopo_consentimento.model_dump(),
                hash_documento=registro.hash_documento,
                assinatura_png=img_bytes,
                data_consentimento=agora,
                commit=False,
            )

            sessao.status = "usado"
            sessao.usado_em = agora
            sessao.ip_assinatura = ip_paciente
            sessao.user_agent_assinatura = user_agent
            sessao.geo_assinatura = geo
            sessao.geo_divergente = geo_divergente
            sessao.id_consentimento = consentimento.id

            # único commit: revogação + consentimento (flush) + sessão
            self.sessao_repo.save(sessao, commit=True)
        except Exception:
            # desfaz revogação + consentimento + sessão (mesma transação)
            self.consentimento_repo.rollback()
            raise

        return {
            "consentimento_uuid": consentimento.uuid,
            "hash_pdf_final": hash_pdf_final,
            "data_consentimento": consentimento.data_consentimento.isoformat(),
            # cópia para o PRÓPRIO paciente (pública, só pelo token, por tempo limitado)
            "download_url": f"/v1/api/pacientes/lgpd/assinar/{token}/comprovante.pdf",
            "copia_valida_ate": (agora + timedelta(minutes=_janela_copia_minutos())).isoformat(),
        }

    # ------------------------------------------- consultas do lado do médico
    def _consentimento_da_empresa_ou_404(self, uuid_consentimento: str, id_empresa: int):
        """404 igual para 'não existe' e 'é de outra empresa' (não vaza existência)."""
        c = self.consentimento_repo.find_by_uuid(uuid_consentimento)
        if not c:
            raise RecursoNaoEncontradoError("Comprovante não encontrado.")
        p = self.paciente_repo.find_by_uuid(c.paciente.uuid, id_empresa)
        if not p or p.id != c.id_paciente:
            raise RecursoNaoEncontradoError("Comprovante não encontrado.")
        return c

    def _sessao_da_empresa_ou_404(self, token: str, id_empresa: int, for_update: bool = False):
        sessao = self.sessao_repo.find_by_token(token, for_update=for_update)
        if not sessao:
            raise RecursoNaoEncontradoError("Link de assinatura não encontrado.")
        p = self.paciente_repo.find_by_uuid(sessao.paciente.uuid, id_empresa)
        if not p or p.id != sessao.id_paciente:
            raise RecursoNaoEncontradoError("Link de assinatura não encontrado.")
        return sessao

    def obter_status_sessao(self, token: str, id_empresa: int) -> dict:
        """Para o médico saber se o paciente já assinou (polling do front)."""
        sessao = self._sessao_da_empresa_ou_404(token, id_empresa)
        status = sessao.status
        if status == "pendente" and self._expirado(sessao):
            status = "expirado"
        dados = {"status": status, "expira_em": sessao.expira_em.isoformat()}
        if status == "usado":
            dados["usado_em"] = sessao.usado_em.isoformat() if sessao.usado_em else None
            dados["consentimento_uuid"] = sessao.consentimento.uuid if sessao.consentimento else None
        return dados

    def cancelar_link(self, token: str, id_empresa: int) -> dict:
        sessao = self._sessao_da_empresa_ou_404(token, id_empresa, for_update=True)
        if sessao.status == "usado":
            raise ConflictoError("Este link já foi utilizado e não pode ser cancelado.")
        sessao.status = "expirado"
        self.sessao_repo.save(sessao, commit=True)
        return {"status": "expirado"}

    def obter_comprovante(self, uuid_consentimento: str, id_empresa: int) -> dict:
        c = self._consentimento_da_empresa_ou_404(uuid_consentimento, id_empresa)
        escopo = c.escopo_consentimento_json or {}
        return {
            "uuid": c.uuid,
            "versao_termo": c.versao_termo,
            "data_consentimento": c.data_consentimento.isoformat(),
            "canal_coleta": c.canal_coleta,
            "status": c.status,
            "hash_documento": c.hash_documento,
            "escopo": escopo.get("escopo", []),   # sem IP/UA/paths internos
            "pdf_url": f"/v1/api/pacientes/lgpd/download-pdf/{c.uuid}" if c.assinatura_png else None,
        }

    def _refazer_pdf(self, c) -> tuple:
        """Refaz em memória o PDF assinado de um consentimento do fluxo digital.
        Retorna (bytes, confere). Usado pelo download do médico e pela cópia do paciente."""
        indisponivel = RecursoNaoEncontradoError("PDF não disponível para este consentimento.")
        j = c.escopo_consentimento_json if isinstance(c.escopo_consentimento_json, dict) else {}
        audit = j.get("audit")
        if not audit:
            raise indisponivel
        pessoal = c.paciente.pessoal
        if pessoal:
            nome = aes_decrypt(pessoal.nome_completo)
            cpf = aes_decrypt(pessoal.cpf) if pessoal.cpf else None
        else:
            nome, cpf = "Titular anonimizado", None   # sem PII: o hash não vai conferir
        data = c.data_consentimento
        if data.tzinfo is None:        # MySQL devolve naive; gravamos em UTC
            data = data.replace(tzinfo=timezone.utc)
        pdf = montar_pdf_assinado(
            texto_termo=audit["texto_integral_aceito"],
            hash_pdf_original=audit["hash_pdf_original"],
            nome=nome, cpf=cpf, versao_termo=c.versao_termo, data=data,
            ip=audit.get("ip"), user_agent=audit.get("user_agent"), geo=audit.get("geolocalizacao"),
            assinatura_png=bytes(c.assinatura_png),
            escopos_aceitos=j.get("escopo", []), escopos_oferecidos=j.get("escopos_oferecidos", []),
        )
        confere = sha256_bytes(pdf) == c.hash_documento
        if not confere:
            logger.warning("PDF refeito do consentimento %s não confere com hash_documento", c.uuid)
        return pdf, confere

    def obter_pdf_assinado(self, uuid_consentimento: str, id_empresa: int) -> tuple:
        """PDF assinado, só se o consentimento é da empresa. Retorna (bytes, confere).

        REFEITO em memória a partir do banco (texto aceito, assinatura PNG, auditoria,
        data); nada é lido nem gravado em disco. confere = SHA-256 refeito == hash_documento
        (pode divergir se reportlab/pypdf/layout mudaram ou se o paciente foi anonimizado).
        Consentimento sem assinatura (registro manual: papel, portal, totem) não tem PDF aqui."""
        c = self._consentimento_da_empresa_ou_404(uuid_consentimento, id_empresa)
        if not c.assinatura_png:
            raise RecursoNaoEncontradoError("PDF não disponível para este consentimento.")
        return self._refazer_pdf(c)