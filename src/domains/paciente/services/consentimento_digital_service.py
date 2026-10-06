"""
Serviço de assinatura digital LGPD — fluxo QR code presencial.

Este service só ORQUESTRA a sessão (token, validação, arquivos). A criação do
Consentimento é delegada ao ConsentimentoService.ativar_novo, para que a regra
"um consentimento ativo por paciente" seja única.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import base64
import binascii
import hashlib
import hmac
import os
import re
import uuid as _uuid

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
from src.core.security import aes_decrypt

def _formatar_cpf(cpf) -> str:
    d = re.sub(r"\D", "", cpf or "")
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else (cpf or "-")


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
        default_path = "./storage/consentimentos"
        
        self.paciente_repo = PacienteRepository()
        self.consentimento_repo = ConsentimentoRepository()
        self.sessao_repo = ConsentimentoSessaoAssinaturaRepository()
        self.consentimento_svc = ConsentimentoService()        
        self.storage_path = Path(os.getenv("CONSENT_STORAGE", default_path))
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.termos_path = Path(os.getenv("CONSENT_PDF_TERMOS", "./storage/termos"))
        self.termos_path.mkdir(parents=True, exist_ok=True)

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

    def _resolver_pdf_termo(self, pdf_termo_path: str) -> Path:
        """O PDF só pode estar dentro de CONSENT_PDF_TERMOS (evita ler/copiar
        arquivos arbitrários do servidor)."""
        try:
            caminho = Path(pdf_termo_path).resolve()
            caminho.relative_to(self.termos_path.resolve())
        except (ValueError, OSError):
            raise DadosInvalidosError("PDF do termo fora do diretório permitido.")
        if caminho.suffix.lower() != ".pdf" or not caminho.is_file():
            raise RecursoNaoEncontradoError("PDF do termo não encontrado no servidor.")
        return caminho

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
        id_unidade: int,
        id_empresa: int,
        versao_termo: str,
        pdf_termo_path: str,
        texto_termo: str,
        ip_medico: str = None,
    ) -> dict:
        try:
            entrada = GerarLinkAssinaturaSchema(
                id_unidade=id_unidade, versao_termo=versao_termo,
                pdf_termo_path=pdf_termo_path, texto_termo=texto_termo,
            )
        except ValidationError as e:
            raise DadosInvalidosError(erros_pydantic_por_campo(e))

        p = self._paciente_ou_404(uuid_paciente, id_empresa)
        nome, cpf = self._identificacao(p)   # falha cedo, antes de expirar links anteriores
        caminho_pdf = self._resolver_pdf_termo(entrada.pdf_termo_path)

        hash_pdf = ConsentimentoSessaoAssinatura.calcular_hash_pdf(str(caminho_pdf))
        agora = datetime.now(timezone.utc)

        # um link pendente por paciente: gerar novo cancela os anteriores
        self.sessao_repo.expirar_pendentes_do_paciente(p.id)

        sessao = ConsentimentoSessaoAssinatura(
            token=ConsentimentoSessaoAssinatura.gerar_token(),
            id_paciente=p.id,
            id_unidade=entrada.id_unidade,
            id_medico_gerador=id_medico,
            versao_termo=entrada.versao_termo,
            pdf_termo_path=str(caminho_pdf),
            hash_pdf_original=hash_pdf,
            texto_termo_snapshot=entrada.texto_termo,
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
            "expira_em": sessao.expira_em.isoformat(),
            "unidade_id": sessao.id_unidade,
        }

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

        base = _uuid.uuid4().hex
        caminho_assinatura = self.storage_path / f"assinatura_{base}.png"
        arquivos_criados = []
        agora = datetime.now(timezone.utc)

        try:
            caminho_assinatura.write_bytes(img_bytes)
            arquivos_criados.append(caminho_assinatura)

            pdf_final_path, hash_pdf_final = self._gerar_pdf_final(
                sessao, caminho_assinatura, base,
                contexto={"ip": ip_paciente, "user_agent": user_agent, "geo": geo, "data": agora},
            )
            arquivos_criados.append(pdf_final_path)

            registro = ConsentimentoDigitalCreateSchema(
                versao_termo=sessao.versao_termo,
                hash_documento=hash_pdf_final,
                escopo_consentimento=EscopoDigitalSchema(
                    escopo=escopos,
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
                pdf_final_path=str(pdf_final_path),
                assinatura_imagem_path=str(caminho_assinatura),
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
            # mesma sessão do SQLAlchemy: o rollback do PacienteRepository desfaz tudo
            self.paciente_repo.rollback()
            for arq in arquivos_criados:
                Path(arq).unlink(missing_ok=True)
            raise

        return {
            "consentimento_uuid": consentimento.uuid,
            "hash_pdf_final": hash_pdf_final,
            "data_consentimento": consentimento.data_consentimento.isoformat(),
            "download_url": f"/v1/api/pacientes/lgpd/comprovante/{consentimento.uuid}",
        }

    def _gerar_pdf_final(self, sessao, caminho_assinatura: Path, nome_base: str, contexto: dict) -> tuple:
        """Termo original + página de assinatura (reportlab desenha a página,
        pypdf junta). Retorna (caminho_final, sha256 do arquivo final).

        O hash final não aparece dentro do PDF (um arquivo não pode conter o
        próprio hash); ele fica no banco (hash_documento) e no comprovante.
        O hash do PDF ORIGINAL aparece na página, ligando as duas versões."""
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader, simpleSplit
        from reportlab.pdfgen import canvas as rl_canvas
        from pypdf import PdfReader, PdfWriter

        nome, cpf = self._identificacao(sessao.paciente)
        agora = contexto["data"]
        try:
            from zoneinfo import ZoneInfo
            data_local = agora.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S (Brasília)")
        except Exception:
            data_local = None
        data_utc = agora.strftime("%d/%m/%Y %H:%M:%S UTC")

        # ---- 1) página de assinatura (em memória)
        buf = BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=A4)
        largura, altura = A4
        margem = 20 * mm
        largura_texto = largura - 2 * margem
        y = altura - margem

        c.setFont("Helvetica-Bold", 15)
        c.drawString(margem, y, "Comprovante de Assinatura Eletrônica")
        y -= 7 * mm
        c.setFont("Helvetica", 9)
        c.drawString(margem, y, "Termo de Consentimento LGPD - Lei 13.709/2018")
        y -= 4 * mm
        c.line(margem, y, largura - margem, y)
        y -= 8 * mm

        def campo(rotulo, valor, y):
            c.setFont("Helvetica-Bold", 9)
            c.drawString(margem, y, rotulo)
            c.setFont("Helvetica", 9)
            linhas = simpleSplit(str(valor or "-"), "Helvetica", 9, largura_texto - 45 * mm) or ["-"]
            for ln in linhas:
                c.drawString(margem + 45 * mm, y, ln)
                y -= 4.5 * mm
            return y - 1.5 * mm

        y = campo("Paciente:", nome, y)
        y = campo("CPF:", _formatar_cpf(cpf), y)
        y = campo("Versão do termo:", sessao.versao_termo, y)
        y = campo("Data/hora:", f"{data_local} - {data_utc}" if data_local else data_utc, y)
        y = campo("IP:", contexto.get("ip"), y)
        y = campo("Dispositivo:", (contexto.get("user_agent") or "")[:300], y)
        y = campo("Localização:", contexto.get("geo"), y)
        y = campo("SHA-256 do termo original:", sessao.hash_pdf_original, y)

        y -= 4 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margem, y, "Assinatura do titular:")
        y -= 3 * mm
        caixa_h = 40 * mm
        c.rect(margem, y - caixa_h, largura_texto, caixa_h)
        img = ImageReader(str(caminho_assinatura))
        iw, ih = img.getSize()
        escala = min((largura_texto - 6 * mm) / iw, (caixa_h - 6 * mm) / ih)
        w, h = iw * escala, ih * escala
        c.drawImage(img, margem + (largura_texto - w) / 2, y - caixa_h + (caixa_h - h) / 2,
                    width=w, height=h, mask="auto")
        y -= caixa_h + 8 * mm

        declaracao = ("Documento assinado eletronicamente pelo titular em atendimento presencial, "
                      "mediante leitura integral do termo, confirmação de identidade e declaração de "
                      "consentimento. A integridade do termo original pode ser verificada pelo hash "
                      "SHA-256 acima.")
        c.setFont("Helvetica-Oblique", 8)
        for ln in simpleSplit(declaracao, "Helvetica-Oblique", 8, largura_texto):
            c.drawString(margem, y, ln)
            y -= 4 * mm
        c.showPage()
        c.save()
        buf.seek(0)

        # ---- 2) junta original + página de assinatura
        writer = PdfWriter()
        for pagina in PdfReader(sessao.pdf_termo_path).pages:
            writer.add_page(pagina)
        for pagina in PdfReader(buf).pages:
            writer.add_page(pagina)

        caminho_final = self.storage_path / f"termo_assinado_{nome_base}.pdf"
        with open(caminho_final, "wb") as f:
            writer.write(f)

        h = hashlib.sha256()
        with open(caminho_final, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return caminho_final, h.hexdigest()

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
            "pdf_url": f"/v1/api/pacientes/lgpd/download-pdf/{c.uuid}" if c.pdf_final_path else None,
        }

    def obter_arquivo_pdf(self, uuid_consentimento: str, id_empresa: int) -> Path:
        """Caminho do PDF assinado, só se o consentimento é da empresa e o
        arquivo está dentro do storage (nada de path vindo do cliente)."""
        c = self._consentimento_da_empresa_ou_404(uuid_consentimento, id_empresa)
        if not c.pdf_final_path:
            raise RecursoNaoEncontradoError("PDF não disponível para este consentimento.")
        try:
            caminho = Path(c.pdf_final_path).resolve()
            caminho.relative_to(self.storage_path.resolve())
        except (ValueError, OSError):
            raise RecursoNaoEncontradoError("PDF não disponível para este consentimento.")
        if not caminho.is_file():
            raise RecursoNaoEncontradoError("Arquivo do PDF não encontrado no servidor.")
        return caminho