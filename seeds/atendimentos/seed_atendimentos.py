"""seed_atendimentos.py -- Etapa 2: leva cada consulta ao estado alvo.

Lê seed_atendimentos.json (gerado por gerar_cenarios.py) e, para cada paciente,
usa os SERVICES reais (mesmas regras, mesmas validações das rotas) para:
  abrir o atendimento -> binário -> [sinais vitais, coleta, input, protocolos,
  conduta] -> finalizar -> encerrar a consulta, conforme `consulta.cenario`:

  em-triagem               triagem aberta + binário (não finaliza)
  aguardando-medico        triagem finalizada
  em-atendimento           avaliação médica aberta (dados do cenário e protocolos)
  encerrada-alta/internacao/transferencia
                           avaliação médica finalizada + consulta encerrada
                           (+ reavaliação nos casos de alergia nova)
  evasao                   triagem aberta + binário + ConsultaService.evadir

Escopo do protocolo: se o catálogo diz `triagem`, o caso roda numa triagem do
enfermeiro (e depois a avaliação médica); caso contrário vai direto à avaliação
médica. Quem atende é sorteado entre médicos/enfermeiros da empresa (--seed).

NÃO é atômico: abrir, binário, finalizar e encerrar comitam sozinhos nos
services. Por isso o seed é idempotente (pula consulta que já tem atendimento)
e, se um paciente falha, cancela o atendimento em andamento e segue. Falha na
1ª etapa deixa a consulta de novo em aguardando-triagem (pode rodar outra vez).

Pré-requisitos: seed_pacientes + seed_consultas já rodados (consulta aberta em
aguardando-triagem, com consentimento dispensado), profissionais cadastrados,
protocolos liberados na empresa e os 7 tipos de sinal vital no LOINC.

Uso:
    python -m src.seeds.seed_atendimentos --empresa 1 --validar   # só confere, não grava
    python -m src.seeds.seed_atendimentos --empresa 1
    python -m src.seeds.seed_atendimentos --empresa 1 --ate 5 --seed 7

Uso (código):
    from src.seeds.seed_atendimentos import seed_atendimentos
    r = seed_atendimentos(empresa=1, validar=True, app=app)
"""

import argparse
import contextlib
import json
import random
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models import db
from src.core.security import hmac_sha256
from src.domains.paciente.repositories.paciente_repository import PacienteRepository
from src.domains.paciente.repositories.alergia_repository import AlergiaRepository
from src.domains.usuario.repository import UsuarioRepository
from src.domains.consulta.repository import ConsultaRepository
from src.domains.consulta.service import ConsultaService
from src.domains.atendimento.service import AtendimentoService
from src.domains.atendimento.repository import AtendimentoRepository
from src.domains.atendimento.contexto_clinico_service import AutorClinico
from src.domains.atendimento.binario.binario_service import BinarioService
from src.domains.atendimento.conduta_enfermagem.service import CondutaEnfermagemService
from src.domains.dados_clinicos.service import DadosClinicosService
from src.domains.dados_clinicos.execucao_atendimento_service import (
    ExecucaoAtendimentoService, ESCOPO_USO_POR_TIPO,
)
from src.domains.paciente.services.alergia_service import AlergiaService
from src.domains.paciente.services.reacao_alergia_service import ReacaoAlergiaService
from src.domains.protocolo.shared.repositories.protocolo_catalogo_repository import ProtocoloCatalogoRepository
from src.domains.empresa.empresa_protocolo.empresa_protocolo_repository import EmpresaProtocoloRepository

JSON_PADRAO = Path(__file__).with_name("seed_atendimentos.json")
SECOES = ("alergias", "medicamentos", "tipo_sanguineo", "doenca_cronica")

CONDUTA_PADRAO = "Sinais vitais aferidos, paciente orientado e encaminhado para avaliação médica."
CONDUTAS = {
    "protocolo": "Protocolo aplicado na triagem; paciente classificado e encaminhado para avaliação médica.",
}


# ============================================================================
# Plano de fases por paciente (usado também no --validar)
# ============================================================================
def _compativel(escopo_uso, tipo_atendimento: str) -> bool:
    return escopo_uso in (None, "ambos", ESCOPO_USO_POR_TIPO.get(tipo_atendimento))


def montar_fases(bloco: dict, escopo_triagem: bool) -> list:
    """Sequência de fases que leva a consulta ao estado alvo.
    Fase de atendimento: {tipo, funcao, dados, finalizar, ...}; ou {encerrar: desfecho} / {evadir: True}."""
    estado = bloco["consulta"]["cenario"]
    desfecho = bloco["consulta"]["desfecho_final"]
    tem_dados = bloco["categoria"] != "basico"
    fases = []

    def triagem(finalizar, dados):
        fases.append({"tipo": "triagem", "funcao": "enfermeiro", "dados": dados, "finalizar": finalizar})

    def medico(finalizar, dados, tipo="avaliacao-medica"):
        fases.append({"tipo": tipo, "funcao": "medico", "dados": dados, "finalizar": finalizar})

    if estado == "em-triagem":
        triagem(False, tem_dados)
    elif estado == "aguardando-medico":
        triagem(True, tem_dados)
    elif estado == "evasao":
        triagem(False, False)
        fases.append({"evadir": True})
    elif estado == "em-atendimento":
        if tem_dados and escopo_triagem:
            triagem(True, True)
            medico(False, False)
        else:
            medico(False, tem_dados)
    elif estado.startswith("encerrada-"):
        if tem_dados and escopo_triagem:
            triagem(True, True)
            medico(True, False)
        else:
            medico(True, tem_dados)
        if bloco.get("reavaliacao"):
            medico(True, False, tipo="reavaliacao")
            fases[-1]["reavaliacao"] = True
        fases.append({"encerrar": desfecho})
    else:
        raise ValueError(f"estado de consulta desconhecido: {estado}")
    return fases


# ============================================================================
# Utilidades
# ============================================================================
class Sorteio:
    """Ciclo embaralhado de ids (mesma ideia do sorteio do seed de pacientes)."""

    def __init__(self, ids, rng):
        self.ids, self.rng, self._fila = list(ids), rng, []

    def proximo(self):
        if not self._fila:
            self._fila = self.ids[:]
            self.rng.shuffle(self._fila)
        return self._fila.pop()


def _achar(obj, chave):
    """Todos os valores de `chave` em qualquer nível de um dict/lista aninhado."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == chave:
                yield v
            yield from _achar(v, chave)
    elif isinstance(obj, list):
        for v in obj:
            yield from _achar(v, chave)


def conferir_esperado(execucao, esperado: dict) -> list:
    """Compara a execução com o gabarito. Devolve a lista de divergências."""
    problemas = []
    resultado = getattr(execucao, "resultado_calculado_json", None) or {}
    if getattr(execucao, "status", "concluida") == "incompleta":
        problemas.append(f"execução incompleta (faltam: {getattr(execucao, 'dados_ausentes_json', None)})")
    if "escore_total" in esperado:
        obtido = next(_achar(resultado, "escore_total"), None)
        if obtido is None or float(obtido) != float(esperado["escore_total"]):
            problemas.append(f"escore_total esperado {esperado['escore_total']}, obtido {obtido}")
        if "override_disparado" in esperado:
            ov = next(_achar(resultado, "override_disparado"), None)
            if ov is not None and bool(ov) != bool(esperado["override_disparado"]):
                problemas.append(f"override esperado {esperado['override_disparado']}, obtido {ov}")
    if "classificacoes_contidas" in esperado:
        obtidas = {v for v in _achar(resultado, "classificacao") if isinstance(v, str)}
        faltam = set(esperado["classificacoes_contidas"]) - obtidas
        if faltam:
            problemas.append(f"classificações ausentes: {sorted(faltam)} (obtidas: {sorted(obtidas)})")
    return problemas


# ============================================================================
# Loader
# ============================================================================
class Loader:
    def __init__(self, empresa: int, validar: bool, seed: int):
        self.empresa, self.validar = empresa, validar
        self.rng = random.Random(seed)
        self.pac_repo = PacienteRepository()
        self.consulta_repo = ConsultaRepository()
        self.atend_repo = AtendimentoRepository()
        self.catalogo = ProtocoloCatalogoRepository()
        self.emp_prot = EmpresaProtocoloRepository()
        self.atend_svc = AtendimentoService()
        self.consulta_svc = ConsultaService()
        self.binario_svc = BinarioService()
        self.dados_svc = DadosClinicosService()
        self.exec_svc = ExecucaoAtendimentoService()
        self.conduta_svc = CondutaEnfermagemService()
        self.alergia_svc = AlergiaService()
        self.reacao_svc = ReacaoAlergiaService()
        self.pool = {}
        self.cache_protocolos = {}
        self.resultado = {"ok": False, "validar": validar, "total": 0, "processados": 0, "pulados": [],
                          "erros": [], "divergencias": [], "avisos": [], "estados": {}, "alertas_interacao": 0}

    # ------------------------------------------------------------ profissionais
    def preparar_profissionais(self):
        for funcao in ("medico", "enfermeiro"):
            ids = [u.id for u in UsuarioRepository().find_by_tipo_papel(self.empresa, funcao)
                   if getattr(u, "status", "ativo") == "ativo"]
            if not ids:
                raise RuntimeError(f"nenhum {funcao} ativo na empresa {self.empresa}")
            self.pool[funcao] = Sorteio(ids, self.rng)

    def _autor(self, funcao: str) -> AutorClinico:
        return AutorClinico(id_usuario=self.pool[funcao].proximo(), funcao_clinica=funcao, id_empresa=self.empresa)

    # ------------------------------------------------------------ protocolos
    def protocolo(self, uuid: str):
        """(catálogo, erro). Confere existência, status e liberação na empresa."""
        if uuid not in self.cache_protocolos:
            cat = self.catalogo.find_by_uuid(uuid)
            erro = None
            if not cat:
                erro = "não encontrado no catálogo"
            elif cat.status != "ativo":
                erro = "não está ativo"
            else:
                vinculo = self.emp_prot.find_por_empresa_e_protocolo(self.empresa, cat.id)
                if not vinculo or not vinculo.ativo:
                    erro = "não está liberado para a empresa"
            self.cache_protocolos[uuid] = (cat, erro)
        return self.cache_protocolos[uuid]

    def _escopo_triagem(self, bloco: dict) -> bool:
        """True se algum protocolo do caso só roda em triagem."""
        for uuid in (bloco["atendimento"].get("protocolos") or []):
            cat, erro = self.protocolo(uuid)
            if cat is not None and cat.escopo_uso == "triagem":
                return True
        return False

    # ------------------------------------------------------------ resolução
    def _resolver(self, bloco: dict):
        """(paciente, consulta) ou levanta _Pular / ValueError."""
        pac = self.pac_repo.find_por_cpf_hash(hmac_sha256(bloco["cpf"]), self.empresa)
        if not pac:
            raise ValueError("paciente não encontrado pelo CPF (seed_pacientes rodou nesta empresa?)")
        if pac.status != "ativo" or pac.falecido:
            raise ValueError(f"paciente não está ativo/vivo (status={pac.status})")
        consulta = self.consulta_repo.find_aberta_por_paciente(pac.id, self.empresa)
        if not consulta:
            raise _Pular("sem consulta aberta (já encerrada, ou seed_consultas não rodou)")
        # Só aguardando-triagem é "ainda não processada". Se uma tentativa anterior falhou, o
        # atendimento foi cancelado e a consulta voltou a esse status: pode rodar de novo.
        if consulta.status_consulta != "aguardando-triagem":
            raise _Pular(f"consulta já processada (status {consulta.status_consulta})")
        return pac, consulta

    # ------------------------------------------------------------ binário
    def _payload_secao(self, secao: str, est_secao: dict, h: dict) -> dict:
        """Cria os itens do CSV se o paciente ainda não tem registro ativo naquela seção;
        senão apenas confirma o que já existe (nunca duplica)."""
        ja_tem = bool(est_secao.get("pre_preenchido"))
        if secao == "tipo_sanguineo":
            if ja_tem:
                return {"possui": True}
            return {"possui": True, "tipo_sanguineo": h["tipo_sanguineo"]["tipo_sanguineo"]}
        possui = h[secao]["possui"]
        if not possui or ja_tem:
            return {"possui": possui}
        itens = [{k: v for k, v in it.items() if k != "reacoes_extras"} for it in h[secao]["itens"]]
        return {"possui": True, "itens": itens}

    def _binario(self, at, pac, h: dict, autor: AutorClinico):
        estado = self.binario_svc.estado(at.uuid, self.empresa)
        for secao in list(estado["pendentes"]):
            payload = self._payload_secao(secao, estado["secoes"][secao], h)
            r = self.binario_svc.conferir_secao(secao, at.uuid, pac.uuid, payload, autor)
            for conferida in r.get("conferidas", []):
                alertas = conferida.get("alertas_interacao") or []
                self.resultado["alertas_interacao"] += len(alertas)
                if secao == "alergias" and conferida.get("itens_criados"):
                    self._reacoes_extras(at, pac, h, autor)

    def _reacoes_extras(self, at, pac, h: dict, autor: AutorClinico):
        """O create de alergia comporta UMA reação; as demais entram pelo service de reação."""
        extras = {it["substancia"]: it.get("reacoes_extras") or [] for it in h["alergias"]["itens"]}
        for alergia in self.alergia_repo_por_paciente(pac.id):
            for reacao in extras.get(alergia.substancia, []):
                self.reacao_svc.adicionar_reacao(at.uuid, pac.uuid, alergia.uuid, reacao, autor)

    @staticmethod
    def alergia_repo_por_paciente(id_paciente):
        return AlergiaRepository().find_por_paciente(id_paciente)

    # ------------------------------------------------------------ dados do cenário
    def _dados(self, at, pac, dados: dict, autor: AutorClinico, tipo: str, esperado: dict, linha, nome):
        if dados.get("sinais_vitais"):
            self.dados_svc.registrar_sinais_vitais(at.uuid, pac.uuid, {"sinais": dados["sinais_vitais"]}, autor)
        horas = dados.get("desde_quando_horas")
        coleta = self.dados_svc.registrar_coleta_clinica(
            at.uuid, pac.uuid, {"desde_quando_sintomas": horas} if horas is not None else {}, autor)
        corpo = {k: v for k, v in {"input_json": dados.get("input_json"),
                                   "queixa_principal": dados.get("queixa_principal"),
                                   "valor_avpu": dados.get("valor_avpu")}.items() if v is not None}
        self.dados_svc.registrar_input_protocolo(at.uuid, pac.uuid, coleta.uuid, corpo, autor)
        for uuid in (dados.get("protocolos") or []):
            cat, erro = self.protocolo(uuid)
            if erro:
                raise RuntimeError(f"protocolo {uuid}: {erro}")
            if not _compativel(cat.escopo_uso, tipo):
                self.resultado["avisos"].append(
                    f"linha {linha}: protocolo {uuid} (escopo {cat.escopo_uso}) não roda em {tipo}; pulado")
                continue
            execucao, _ = self.exec_svc.executar(at.uuid, pac.uuid, uuid, autor)
            for problema in conferir_esperado(execucao, (esperado or {}).get("protocolos", {}).get(uuid, {})):
                self.resultado["divergencias"].append({"linha": linha, "paciente": nome, "divergencia": problema})

    # ------------------------------------------------------------ uma fase de atendimento
    def _fase_atendimento(self, fase, bloco, pac, consulta, registros):
        autor = self._autor(fase["funcao"])
        abrir = {"triagem": self.atend_svc.abrir_triagem, "avaliacao-medica": self.atend_svc.abrir_avaliacao_medica,
                 "reavaliacao": self.atend_svc.abrir_reavaliacao}[fase["tipo"]]
        at = abrir(consulta.uuid, autor.id_usuario, self.empresa)
        reav = bloco.get("reavaliacao") if fase["tipo"] == "reavaliacao" else None
        duracao = (reav["duracao_min"] if reav else bloco["atendimento"].get(
            "duracao_triagem_min" if fase["tipo"] == "triagem" else "duracao_min", 10))
        registros.append({"uuid": at.uuid, "tipo": fase["tipo"], "duracao": duracao,
                          "finalizar": fase["finalizar"], "dias_apos": reav["dias_apos"] if reav else None})

        self._binario(at, pac, bloco["historico"], autor)
        if reav:
            for nova in reav["novas_alergias"]:
                self.alergia_svc.adicionar_alergia(at.uuid, pac.uuid, nova, autor)
            self._dados(at, pac, {"sinais_vitais": reav["sinais_vitais"], "desde_quando_horas": reav["desde_quando_horas"],
                                  "queixa_principal": reav["queixa_principal"]}, autor, fase["tipo"], None,
                        bloco["linha_csv"], bloco["nome"])
        elif fase["dados"]:
            self._dados(at, pac, bloco["atendimento"], autor, fase["tipo"], bloco.get("esperado"),
                        bloco["linha_csv"], bloco["nome"])
        if fase["tipo"] == "triagem" and (fase["dados"] or fase["finalizar"]):
            conduta = CONDUTAS["protocolo"] if bloco["atendimento"].get("protocolos") else CONDUTA_PADRAO
            self.conduta_svc.registrar(at.uuid, pac.uuid, {"descricao_conduta": conduta}, autor)
        if fase["finalizar"]:
            self.atend_svc.finalizar(at.uuid, self.empresa, autor.id_usuario, eh_medico=(fase["funcao"] == "medico"))
        return autor

    # ------------------------------------------------------------ datas
    def _carimbar(self, consulta_uuid, registros, dias_atras, encerrada):
        """Os services carimbam 'agora'; aqui as datas voltam para `dias_atras` (início/fim do
        atendimento e da consulta). Nada a fazer para consultas de hoje."""
        if not dias_atras or not registros:
            return
        agora = datetime.now(timezone.utc)
        base = (agora - timedelta(days=dias_atras)).replace(
            hour=self.rng.randint(8, 17), minute=self.rng.randint(0, 59), second=0, microsecond=0)
        cursor = base
        for r in registros:
            if r["tipo"] == "reavaliacao":
                inicio = max(base + timedelta(days=r["dias_apos"] or 1, minutes=self.rng.randint(0, 120)),
                             cursor + timedelta(hours=1))
            else:
                inicio = cursor + timedelta(minutes=self.rng.randint(3, 25))
            fim = inicio + timedelta(minutes=r["duracao"])
            at = self.atend_repo.find_by_uuid(r["uuid"], id_empresa=self.empresa)
            at.data_hora_inicio = inicio
            at.data_hora_fim = fim if r["finalizar"] else at.data_hora_fim
            self.atend_repo.save(at, commit=False)
            cursor = fim
        c = self.consulta_repo.find_by_uuid(consulta_uuid, self.empresa)
        c.data_hora_inicio = base
        if encerrada:
            c.data_hora_fim = cursor + timedelta(minutes=self.rng.randint(2, 10))
        self.consulta_repo.save(c, commit=False)
        db.session.commit()

    # ------------------------------------------------------------ um paciente
    def processar(self, bloco: dict):
        pac, consulta = self._resolver(bloco)
        fases = montar_fases(bloco, self._escopo_triagem(bloco))
        if self.validar:
            for uuid in (bloco["atendimento"].get("protocolos") or []):
                _, erro = self.protocolo(uuid)
                if erro:
                    raise ValueError(f"protocolo {uuid}: {erro}")
            return {"fases": [f.get("tipo") or ("evadir" if f.get("evadir") else "encerrar") for f in fases]}

        registros, ultimo_autor, encerrada = [], None, False
        try:
            for fase in fases:
                if "encerrar" in fase:
                    self.consulta_svc.encerrar(consulta.uuid, fase["encerrar"], ultimo_autor.id_usuario, self.empresa)
                    encerrada = True
                elif "evadir" in fase:
                    self.consulta_svc.evadir(consulta.uuid, ultimo_autor.id_usuario, self.empresa)
                    encerrada = True
                else:
                    ultimo_autor = self._fase_atendimento(fase, bloco, pac, consulta, registros)
            self._carimbar(consulta.uuid, registros, bloco["consulta"]["dias_atras"], encerrada)
        except Exception:
            self._limpar_falha(consulta.uuid)
            raise
        return {"fases": [r["tipo"] for r in registros]}

    def _limpar_falha(self, consulta_uuid):
        """Cancela o atendimento deixado em andamento para não travar a consulta."""
        db.session.rollback()
        try:
            c = self.consulta_repo.find_by_uuid(consulta_uuid, self.empresa)
            for a in self.atend_repo.find_por_consulta(c.id):
                if a.status == "em-andamento":
                    self.atend_svc.cancelar(a.uuid, self.empresa, a.realizado_por, motivo="outro")
        except Exception as e:  # limpeza é melhor esforço
            db.session.rollback()
            self.resultado["avisos"].append(f"consulta {consulta_uuid}: não consegui cancelar o atendimento em andamento ({e})")


class _Pular(Exception):
    pass


# ============================================================================
def _msg(e: Exception) -> str:
    return f"{type(e).__name__}: {getattr(e, 'message', None) or getattr(e, 'orig', None) or e}"


def seed_atendimentos(empresa: int, ate: int = None, validar: bool = False,
                      seed: int = 2026, app=None) -> dict:
    """Executa o seed e devolve um relatório (não levanta exceção por paciente)."""
    ctx = app.app_context() if app is not None else contextlib.nullcontext()
    with ctx:
        json_path="seeds/atendimentos/seed_atendimentos.json"
        return _executar(empresa, json_path, ate, validar, seed)


def _executar(empresa, json_path, ate, validar, seed) -> dict:
    loader = Loader(empresa, validar, seed)
    r = loader.resultado
    caminho = Path(json_path) if json_path else JSON_PADRAO
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except Exception as e:
        r["erros"].append({"linha": 0, "paciente": "-", "erro": f"falha lendo {caminho}: {_msg(e)}"})
        return r
    blocos = dados["pacientes"][:ate] if ate else dados["pacientes"]
    r["total"] = len(blocos)
    try:
        loader.preparar_profissionais()
    except Exception as e:
        r["erros"].append({"linha": 0, "paciente": "-", "erro": _msg(e)})
        return r

    estados = Counter()
    for bloco in blocos:
        ident = {"linha": bloco["linha_csv"], "paciente": bloco["nome"]}
        try:
            loader.processar(bloco)
            r["processados"] += 1
            estados[bloco["consulta"]["cenario"]] += 1
        except _Pular as e:
            r["pulados"].append({**ident, "motivo": str(e)})
        except Exception as e:
            db.session.rollback()
            r["erros"].append({**ident, "erro": _msg(e)})
    r["estados"] = dict(sorted(estados.items()))
    r["ok"] = not r["erros"] and not r["divergencias"]
    return r


def _imprimir(r: dict):
    modo = "VALIDAÇÃO (nada gravado)" if r["validar"] else "EXECUÇÃO"
    print(f"{modo}: {r['processados']}/{r['total']} pacientes; {len(r['pulados'])} pulado(s); "
          f"{len(r['erros'])} erro(s); {len(r['divergencias'])} divergência(s) de protocolo.")
    for estado, n in r["estados"].items():
        print(f"  {estado:<26}{n:>4}")
    if r["alertas_interacao"]:
        print(f"alertas de interação medicamentosa gerados: {r['alertas_interacao']}")
    for p in r["pulados"][:10]:
        print(f"  pulado: linha {p['linha']} ({p['paciente']}): {p['motivo']}")
    for e in r["erros"]:
        print(f"  ERRO linha {e['linha']} ({e['paciente']}): {e['erro']}")
    for d in r["divergencias"]:
        print(f"  DIVERGÊNCIA linha {d['linha']} ({d['paciente']}): {d['divergencia']}")
    for a in r["avisos"]:
        print(f"  AVISO: {a}")


def main(empresa, ate, validar, seed):
    ap = argparse.ArgumentParser()
    ap.add_argument("--empresa", type=int, required=True)
    ap.add_argument("--ate", type=int, default=None, help="só os N primeiros pacientes (teste)")
    ap.add_argument("--validar", action="store_true", help="confere tudo sem gravar")
    ap.add_argument("--seed", type=int, default=2026, help="sorteio de profissionais e horários")
    args = ap.parse_args()

    r = seed_atendimentos(empresa=args.empresa, ate=args.ate, validar=args.validar, seed=args.seed)
    _imprimir(r)
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()