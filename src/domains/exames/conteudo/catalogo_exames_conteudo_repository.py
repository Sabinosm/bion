from typing import List, Optional

from src.models.catalogos.catalogo_exames_conteudo import CatalogoExamesConteudo

# Seções que importam para a IA entender o exame, nesta ordem.
CHAVES_PARA_IA = ("o_que_e", "para_que_serve", "por_que_pedir", "preparo", "resultados")
FONTE_LEGIVEL = "MedlinePlus (U.S. National Library of Medicine)"


class CatalogoExamesConteudoRepository:

    def find_por_exame(self, id_catalogo_exame: int, idioma: str = "en") -> List[CatalogoExamesConteudo]:
        return (
            CatalogoExamesConteudo.query
            .filter_by(id_catalogo_exame=id_catalogo_exame, idioma=idioma)
            .order_by(CatalogoExamesConteudo.tipo.asc(), CatalogoExamesConteudo.id.asc())  # 'exame' antes de 'topico'
            .all()
        )

    def contexto_para_ia(self, id_catalogo_exame: int, idioma: str = "en", max_chars: int = 4000) -> Optional[dict]:
        """Texto compacto sobre o exame (o que é, para que serve, por que pedir, preparo, resultados),
        cortado em fronteira de seção. None se não há página de exame guardada.

        É conteúdo voltado ao paciente e de base americana: a IA deve tratá-lo como contexto geral,
        não como protocolo brasileiro."""
        pagina = next((c for c in self.find_por_exame(id_catalogo_exame, idioma) if c.tipo == "exame"), None)
        if not pagina:
            return None
        por_chave = {}
        for s in pagina.secoes_json or []:
            if s.get("chave") and s["chave"] not in por_chave:
                por_chave[s["chave"]] = s
        partes = [f"{pagina.titulo}"]
        if pagina.outros_nomes_json:
            partes.append("Other names: " + ", ".join(pagina.outros_nomes_json))
        tamanho = sum(len(p) for p in partes)
        for chave in CHAVES_PARA_IA:
            s = por_chave.get(chave)
            if not s:
                continue
            bloco = f"{s['titulo']}\n{s['texto']}"
            if tamanho + len(bloco) > max_chars:
                break
            partes.append(bloco)
            tamanho += len(bloco)
        return {
            "texto": "\n\n".join(partes),
            "fonte": FONTE_LEGIVEL,
            "url": pagina.url,
            "idioma": pagina.idioma,
            "buscado_em": pagina.buscado_em.isoformat() if pagina.buscado_em else None,
        }
