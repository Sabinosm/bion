"""avaliar_ia.py -- envia os casos da colinha à IA e guarda as respostas.

Fluxo, por caso (usa o MESMO serviço que a rota POST /atendimento/<uuid>/avaliacao-bion):
  CPF -> paciente -> consulta aberta -> avaliação médica em andamento
  -> AvaliacaoBionService.iniciar(...)  -> acompanha o status até concluir
  -> lê OutputBion (output_ia_json, índices) -> resolve o NOME dos itens de catálogo.

O catálogo NÃO precisa ser enviado a ninguém: este script roda dentro do seu projeto e consulta
só os UUIDs que a IA devolveu (medicamentos e exames), guardando o texto em `respostas_ia.json`.
O classificador (classificar_avaliacao.py) lê esse arquivo e funciona offline.

Ritmo: lotes de 5 (--lote) a cada 60 s (--intervalo). 40 casos = 8 lotes, cerca de 8 minutos.
Retomável: o que já concluiu é pulado (use --refazer para reenviar tudo).

Uso (da raiz do projeto, com o app configurado):
    python -m src.seeds.avaliar_ia --empresa 1 --validar          # só confere os atendimentos
    python -m src.seeds.avaliar_ia --empresa 1 --ate 2            # teste com 2 casos
    python -m src.seeds.avaliar_ia --empresa 1                    # os 40, e já classifica
    python -m src.seeds.avaliar_ia --empresa 1 --gravar-notas     # grava o nível como avaliacao_nota

Uso (código):
    from src.seeds.avaliar_ia import avaliar_ia
    avaliar_ia(empresa=1, app=app)

Pré-requisito: os 40 atendimentos em andamento (avaliação médica) com input registrado, criados pelos
seeds com os arquivos avaliacao_*.
"""

import argparse
import contextlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

try:
    import classificar_avaliacao as C
except ImportError:  # rodando como arquivo solto
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import classificar_avaliacao as C

AQUI = Path(__file__).resolve().parent
COLINHA_PADRAO = AQUI / "colinha_avaliacao.json"
RESPOSTAS_PADRAO = AQUI / "respostas_ia.json"
RESULTADO_PADRAO = AQUI / "resultado_avaliacao.json"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


# ============================================================================
# Ponte com o projeto (isolada para poder ser trocada nos testes)
# ============================================================================
class ProjetoReal:
    def __init__(self, empresa: int, servico=None):
        from sqlalchemy import inspect as sa_inspect
        from src.models import db
        from src.core.security import hmac_sha256
        from src.domains.paciente.repositories.paciente_repository import PacienteRepository
        from src.domains.consulta.repository import ConsultaRepository
        from src.domains.atendimento.repository import AtendimentoRepository
        self.empresa, self.db, self.hmac, self._inspect = empresa, db, hmac_sha256, sa_inspect
        self.pac_repo, self.consulta_repo, self.atend_repo = PacienteRepository(), ConsultaRepository(), AtendimentoRepository()
        self.servico = servico or self._descobrir_servico()

    @staticmethod
    def _descobrir_servico():
        """Reaproveita o MESMO serviço da rota (singleton do controller do Bion)."""
        for modulo in list(sys.modules.values()):
            if hasattr(modulo, "bp_bion") and callable(getattr(modulo, "servico", None)):
                return modulo.servico()
        raise RuntimeError("Não achei o controller do Bion carregado. Crie o app (importando as rotas) antes de rodar, "
                           "ou passe servico=AvaliacaoBionService(...) para ProjetoReal.")

    # ------------------------------------------------------------ atendimento
    def localizar_atendimento(self, cpf: str):
        pac = self.pac_repo.find_por_cpf_hash(self.hmac(cpf), self.empresa)
        if not pac:
            raise LookupError("paciente não encontrado pelo CPF")
        consulta = self.consulta_repo.find_aberta_por_paciente(pac.id, self.empresa)
        if not consulta:
            raise LookupError("paciente sem consulta aberta")
        abertos = [a for a in self.atend_repo.find_por_consulta(consulta.id)
                   if a.status == "em-andamento" and a.tipo_atendimento == "avaliacao-medica"]
        if not abertos:
            raise LookupError(f"sem avaliação médica em andamento (consulta em {consulta.status_consulta})")
        return NS(uuid=abertos[-1].uuid, id_usuario=abertos[-1].realizado_por)

    # ------------------------------------------------------------ IA
    def iniciar(self, at) -> str:
        out = self.servico.iniciar(at.uuid, self.empresa, at.id_usuario, eh_medico=True)
        return out.uuid

    def status(self, uuid_output: str, id_usuario: int) -> dict:
        return self.servico.status(uuid_output, self.empresa, id_usuario)

    def _modelo(self, padrao: str):
        for m in self.db.Model.registry.mappers:
            if re.fullmatch(padrao, m.class_.__name__, re.I):
                return m.class_
        return None

    def ler(self, uuid_output: str) -> dict:
        Out = self._modelo(r"OutputBion")
        self.db.session.expire_all()  # a resposta é gravada por outra sessão/thread
        row = Out.query.filter_by(uuid=uuid_output).first()
        num = lambda x: float(x) if x is not None else None  # noqa: E731
        return {"status": row.status, "erro": row.erro_codigo, "output_ia": row.output_ia_json,
                "indice_completude": num(row.indice_completude), "indice_confianca": num(row.indice_confianca),
                "versao_modelo_ia": row.versao_modelo_ia,
                "concluido_em": row.concluido_em.isoformat() if row.concluido_em else None}

    # ------------------------------------------------------------ catálogo (só os UUIDs da resposta)
    def _texto_registro(self, modelo, uuid: str):
        mapper = self._inspect(modelo)
        attr = next((a.key for a in mapper.column_attrs if a.key == "uuid"), None) or \
            next((a.key for a in mapper.column_attrs if "uuid" in a.key), None)
        if not attr:
            return None
        obj = self.db.session.query(modelo).filter(getattr(modelo, attr) == uuid).first()
        if not obj:
            return None
        valores = [getattr(obj, a.key) for a in mapper.column_attrs]
        return " | ".join(v.strip()[:200] for v in valores if isinstance(v, str) and v.strip() and not _UUID.match(v.strip()))

    def resolver_catalogo(self, output_ia: dict) -> dict:
        proposta = (output_ia or {}).get("proposta") or {}
        modelos = {"medicamento": self._modelo(r"CatalogoMedicamentos?"),
                   "exame": self._modelo(r"(catalogo.*exame.*|exame.*catalogo.*)")}
        mapa = {}
        for tipo, chave in (("medicamento", "medicamentos"), ("exame", "exames")):
            for it in (proposta.get(chave) or []):
                uuid = it.get("uuid_catalogo") or it.get("uuid_exame") or it.get("uuid")
                if uuid and uuid not in mapa and modelos[tipo] is not None:
                    mapa[uuid] = {"tipo": tipo, "texto": self._texto_registro(modelos[tipo], uuid)}
        return mapa

    # ------------------------------------------------------------ nota
    def avaliar_nota(self, uuid_output: str, id_usuario: int, nota: float, descricao: str):
        from src.domains.output_ia import AvaliacaoNotaIn
        corpo = AvaliacaoNotaIn(avaliacao_nota=nota, avaliacao_nota_descricao=descricao)
        return self.servico.avaliar_nota(uuid_output, self.empresa, id_usuario, corpo)


# ============================================================================
# Coleta
# ============================================================================
def _agora_iso():
    return datetime.now(timezone.utc).isoformat()


def _carregar(caminho: Path) -> dict:
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8")).get("respostas", {})
    return {}


def _salvar(caminho: Path, respostas: dict):
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps({"atualizado_em": _agora_iso(), "respostas": respostas}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(caminho)


def validar(casos: list, projeto) -> list:
    """Confere se cada caso tem avaliação médica em andamento. Devolve [(id, problema)]."""
    problemas = []
    for c in casos:
        try:
            projeto.localizar_atendimento(c["cpf"])
        except Exception as e:
            problemas.append((c["id"], f"{type(e).__name__}: {e}"))
    return problemas


def coletar(casos: list, projeto, saida: Path, lote: int = 5, intervalo: float = 60.0, timeout: float = 240.0,
            poll: float = 3.0, refazer: bool = False, ate: int = None, dormir=time.sleep, relogio=time.monotonic,
            log=print) -> dict:
    respostas = _carregar(saida)
    pendentes = [c for c in casos if refazer or (respostas.get(c["id"]) or {}).get("status") != "concluido"]
    if ate:
        pendentes = pendentes[:ate]
    log(f"{len(pendentes)} caso(s) a enviar, em lotes de {lote} a cada {intervalo:.0f}s "
        f"({len(casos) - len(pendentes)} já concluídos).")

    for inicio in range(0, len(pendentes), lote):
        t0 = relogio()
        em_curso = {}
        for c in pendentes[inicio:inicio + lote]:
            rec = {"id": c["id"], "enviado_em": _agora_iso()}
            try:
                at = projeto.localizar_atendimento(c["cpf"])
                rec.update(uuid_output=projeto.iniciar(at), id_usuario=at.id_usuario, status="processando")
                em_curso[c["id"]] = (rec, t0)
            except Exception as e:  # 409 sem input, 403, atendimento ausente, etc.
                rec.update(status="erro_envio", erro=f"{type(e).__name__}: {getattr(e, 'message', None) or e}")
            respostas[c["id"]] = rec

        limite = relogio() + timeout
        while em_curso and relogio() < limite:
            for cid, (rec, t_ini) in list(em_curso.items()):
                try:
                    st = projeto.status(rec["uuid_output"], rec["id_usuario"])
                except Exception as e:
                    rec.update(status="erro_status", erro=f"{type(e).__name__}: {e}")
                    del em_curso[cid]
                    continue
                if st.get("status") in ("concluido", "falhou"):
                    lido = projeto.ler(rec["uuid_output"])
                    rec.update(lido)
                    rec["duracao_s"] = round(relogio() - t_ini, 1)
                    rec["catalogo"] = projeto.resolver_catalogo(lido.get("output_ia")) if lido.get("status") == "concluido" else {}
                    if lido.get("status") == "falhou":
                        rec["erro"] = st.get("erro_codigo") or lido.get("erro")
                    del em_curso[cid]
            if em_curso:
                dormir(poll)
        for cid, (rec, _) in em_curso.items():
            rec.update(status="timeout", erro=f"sem resposta em {timeout:.0f}s")

        _salvar(saida, respostas)
        feitos = min(inicio + lote, len(pendentes))
        log(f"  lote {inicio // lote + 1}: {feitos}/{len(pendentes)} | "
            + ", ".join(f"{k}={v}" for k, v in _contagem(respostas, [c['id'] for c in pendentes[:feitos]]).items()))
        if inicio + lote < len(pendentes):
            dormir(max(0.0, intervalo - (relogio() - t0)))
    return respostas


def _contagem(respostas: dict, ids: list) -> dict:
    cont = {}
    for i in ids:
        s = (respostas.get(i) or {}).get("status", "?")
        cont[s] = cont.get(s, 0) + 1
    return cont


# ============================================================================
# Orquestração
# ============================================================================
def avaliar_ia(empresa: int, colinha: Path = None, respostas: Path = None, resultado: Path = None,
               lote: int = 5, intervalo: float = 60.0, timeout: float = 240.0, ate: int = None, refazer: bool = False,
               somente_validar: bool = False, classificar: bool = True, gravar_notas: bool = False,
               app=None, projeto=None) -> dict:
    ctx = app.app_context() if app is not None else contextlib.nullcontext()
    with ctx:
        colinha_p, respostas_p = Path(colinha or COLINHA_PADRAO), Path(respostas or RESPOSTAS_PADRAO)
        resultado_p = Path(resultado or RESULTADO_PADRAO)
        casos = json.loads(colinha_p.read_text(encoding="utf-8"))["casos"]
        projeto = projeto or ProjetoReal(empresa)

        if somente_validar:
            problemas = validar(casos, projeto)
            return {"ok": not problemas, "problemas": problemas, "total": len(casos)}

        coletar(casos, projeto, respostas_p, lote, intervalo, timeout, refazer=refazer, ate=ate)
        saida = {"ok": True, "respostas": str(respostas_p)}
        if classificar:
            colinha_dados = json.loads(colinha_p.read_text(encoding="utf-8"))
            resultados = C.classificar_tudo(colinha_dados, _carregar(respostas_p))
            resumo = C.resumir(resultados)
            resultado_p.write_text(json.dumps({"resumo": resumo, "casos": resultados}, ensure_ascii=False, indent=2), encoding="utf-8")
            resultado_p.with_name("relatorio_avaliacao.md").write_text(C.relatorio_md(resultados, resumo), encoding="utf-8")
            saida.update(resumo=resumo)
            if gravar_notas:
                saida["notas"] = gravar(resultados, projeto)
        return saida


def gravar(resultados: list, projeto) -> dict:
    """Grava o nível (1 a 5) como OutputBion.avaliacao_nota + descrição. Só casos com nível."""
    ok, erros = 0, []
    for r in resultados:
        if not r.get("nivel") or not r.get("uuid_output"):
            continue
        nota, descricao = C.NOTA_POR_NIVEL[r["nivel"]]
        try:
            projeto.avaliar_nota(r["uuid_output"], r["id_usuario"], nota, descricao)
            ok += 1
        except Exception as e:
            erros.append((r["id"], f"{type(e).__name__}: {e}"))
    return {"gravadas": ok, "erros": erros}


def _obter_app():
    try:
        from src.main import app
        return app
    except ImportError:
        from src.main import create_app
        return create_app()


def main(app):
    ap = argparse.ArgumentParser()
    ap.add_argument("--empresa", type=int, required=True)
    ap.add_argument("--colinha", default=str(COLINHA_PADRAO))
    ap.add_argument("--respostas", default=str(RESPOSTAS_PADRAO))
    ap.add_argument("--lote", type=int, default=5)
    ap.add_argument("--intervalo", type=float, default=60.0, help="segundos entre o início de um lote e o próximo")
    ap.add_argument("--timeout", type=float, default=240.0, help="espera máxima por lote")
    ap.add_argument("--ate", type=int, default=None, help="só os N primeiros casos pendentes")
    ap.add_argument("--refazer", action="store_true", help="reenvia também os já concluídos")
    ap.add_argument("--validar", action="store_true", help="só confere se os atendimentos estão prontos")
    ap.add_argument("--sem-classificar", action="store_true")
    ap.add_argument("--gravar-notas", action="store_true", help="grava o nível como avaliacao_nota no OutputBion")
    a = ap.parse_args()

    r = avaliar_ia(a.empresa, Path(a.colinha), Path(a.respostas), None, a.lote, a.intervalo, a.timeout, a.ate, a.refazer,
                   a.validar, not a.sem_classificar, a.gravar_notas, app=app)
    if a.validar:
        print(f"{r['total'] - len(r['problemas'])}/{r['total']} atendimentos prontos.")
        for i, p in r["problemas"]:
            print(f"  - {i}: {p}")
        sys.exit(0 if r["ok"] else 1)
    if "resumo" in r:
        s = r["resumo"]
        print(f"média do nível {s['media_nivel']} | N4/N5 {s['pct_nivel_4_ou_5']}% | falhas de segurança {len(s['falhas_seguranca'])} "
              f"| falhas técnicas {len(s['falhas_tecnicas'])}  -> relatorio_avaliacao.md")
    if r.get("notas"):
        print("notas gravadas:", r["notas"])


if __name__ == "__main__":
    main()
