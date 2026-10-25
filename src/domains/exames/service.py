from sqlalchemy.exc import IntegrityError

from src.core.exceptions import RecursoNaoEncontradoError, DadosInvalidosError
from src.models import db
from .repository import CatalogoExamesRepository
from .normalizacao import normalizar_texto
from .conteudo.catalogo_exames_conteudo_repository import (
    CatalogoExamesConteudoRepository, FONTE_LEGIVEL,
)

TIPOS_VALIDOS = ("laboratorial", "imagem", "funcional", "outro")
IDIOMAS_CONTEUDO = ("en", "es")
JEJUM_MAX_HORAS = 72  # limite de sanidade para o cadastro; ajuste se precisar

AVISO_CONTEUDO = (
    "Conteúdo de apoio voltado ao paciente e de base americana (MedlinePlus). "
    "Use como contexto geral, não como protocolo brasileiro."
)


class CatalogoExamesService:

    def __init__(self):
        self.repo = CatalogoExamesRepository()
        self.repo_conteudo = CatalogoExamesConteudoRepository()

    def buscar_por_uuid(self, uuid: str):
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"Exame não encontrado: {uuid}")
        return e

    def listar(self):
        return self.repo.find_all()

    def buscar(self, termo: str):
        return self.repo.buscar_por_nome(termo)

    def listar_filtros(self) -> dict:
        """Valores para popular os filtros da tela (tipos fixos + materiais existentes)."""
        return {"tipos": list(TIPOS_VALIDOS), "materiais": self.repo.listar_materiais()}

    def listar_paginado(self, termo, tipo, pagina: int, por_pagina: int,
                        material=None, exige_jejum=None):
        """Busca do médico: exames ativos, por nome (pt/en) ou sinônimo.

        Filtros opcionais: tipo, material (valor de listar_filtros) e
        exige_jejum (True: jejum > 0 h; False: sem jejum)."""
        if tipo and tipo not in TIPOS_VALIDOS:
            raise DadosInvalidosError(f"tipo inválido: use {', '.join(TIPOS_VALIDOS)}.")
        material = (material or "").strip() or None
        return self.repo.listar_paginado(termo, tipo, pagina, por_pagina, material, exige_jejum)

    def conteudo_de_apoio(self, uuid: str, idioma: str = "en") -> dict:
        """Conteúdo do MedlinePlus já guardado (o app nunca consulta a fonte durante o
        atendimento). Sem conteúdo no idioma pedido não é erro: devolve disponivel=False."""
        idioma = (idioma or "en").strip().lower()
        if idioma not in IDIOMAS_CONTEUDO:
            raise DadosInvalidosError(f"idioma inválido: use {', '.join(IDIOMAS_CONTEUDO)}.")
        exame = self.buscar_por_uuid(uuid)
        paginas = self.repo_conteudo.find_por_exame(exame.id, idioma)  # 'exame' antes de 'topico'
        if not paginas:
            return {"disponivel": False, "idioma": idioma}
        return {
            "disponivel": True,
            "idioma": idioma,
            "fonte": FONTE_LEGIVEL,
            "aviso": AVISO_CONTEUDO,
            "paginas": [self._pagina_para_dict(p) for p in paginas],
        }

    @staticmethod
    def _pagina_para_dict(p) -> dict:
        return {
            "tipo": p.tipo,
            "titulo": p.titulo,
            "url": p.url,
            "outros_nomes": p.outros_nomes_json or [],
            "secoes": p.secoes_json or [],
            "atribuicao": p.atribuicao,
            "buscado_em": p.buscado_em.isoformat() if p.buscado_em else None,
        }

    def criar(self, dados: dict):
        from src.models.catalogos.catalogo_exames import CatalogoExames

        nome = (dados.get("nome_exame") or "").strip()
        if not nome:
            raise DadosInvalidosError("nome_exame é obrigatório.")

        tipo = dados.get("tipo")
        if tipo and tipo not in TIPOS_VALIDOS:
            raise DadosInvalidosError(f"tipo inválido: use {', '.join(TIPOS_VALIDOS)}.")

        jejum = dados.get("jejum_horas")
        if jejum is not None and (
                not isinstance(jejum, int) or isinstance(jejum, bool)
                or not 0 <= jejum <= JEJUM_MAX_HORAS):
            raise DadosInvalidosError(
                f"jejum_horas deve ser um inteiro entre 0 e {JEJUM_MAX_HORAS}.")

        sinonimos = dados.get("sinonimos") or []
        if not isinstance(sinonimos, list) or not all(isinstance(s, str) for s in sinonimos):
            raise DadosInvalidosError("sinonimos deve ser uma lista de textos.")
        sinonimos = [s.strip() for s in sinonimos if s.strip()]

        nome_en = (dados.get("nome_exame_en") or "").strip() or None
        nome_norm = normalizar_texto(nome)
        if self.repo.find_por_nome_normalizado(nome_norm):
            raise DadosInvalidosError("Já existe um exame com esse nome.")

        # mesmo formato da importação: nome pt | nome en | sinônimos, normalizados
        busca = " | ".join(dict.fromkeys(
            normalizar_texto(t) for t in [nome, nome_en, *sinonimos] if t))

        e = CatalogoExames(
            nome_exame=nome,
            nome_exame_en=nome_en,
            nome_normalizado=nome_norm,
            busca_normalizada=busca,
            sinonimos_busca_json=sinonimos or None,
            codigo_tuss=dados.get("codigo_tuss"),
            codigo_loinc=dados.get("codigo_loinc"),
            tipo=tipo,
            material=dados.get("material"),
            material_en=dados.get("material_en"),
            jejum_horas=jejum,
            observacoes=dados.get("observacoes"),
        )
        try:
            return self.repo.save(e)
        except IntegrityError:
            db.session.rollback()
            raise DadosInvalidosError(
                "Não foi possível cadastrar: confira se o exame já existe e se o "
                "codigo_loinc existe na referência LOINC.")