"""Avaliacao Bion, assincrona.

  iniciar()   (na requisicao)  valida, cria a linha de OutputBion com status='processando',
                               enfileira e devolve na hora.
  processar() (no worker)      roda o laco com a IA, grava a resposta, cria o rascunho e
                               troca os rascunhos antigos da IA.
  consultar() (na requisicao)  status e, se concluido, o output_front.

Pre-requisito: o atendimento precisa ter um input de protocolo registrado (o vigente e o
de maior id); sem ele, iniciar() devolve 409 e nada e enfileirado.

Regras: so o MEDICO da avaliacao medica ou da reavaliacao em andamento (TIPOS_COM_BION) usa a IA (o rascunho sai em nome
de quem fez o atendimento). Enfermeiro/triagem seguem sem IA, pelos protocolos.

Status de OutputBion: processando -> concluido | falhou (+ erro_codigo).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.core.exceptions import ConflictoError, PermissaoNegadaError, RecursoNaoEncontradoError

from src.domains.input_ia import Config, InputModel
from src.domains.output_ia import (OutputIA, colunas_envio, colunas_resposta, montar_output_front)
from .repository import OutputBionRepository
from .helpers.avaliador import avaliar
from .helpers.dependencias import Dependencias
from .helpers.executor import ExecutorThread
from .helpers.status import (CONCLUIDO, FALHOU, FILA_INDISPONIVEL, INTERNO, PROCESSANDO, REGISTRO_PROPOSTA)
from .helpers.tarefa import Tarefa

log = logging.getLogger(__name__)

TTL_PROCESSANDO = timedelta(minutes=10)
TIPOS_COM_BION = ("avaliacao-medica", "reavaliacao")


class AvaliacaoBionService:

    def __init__(self, deps: Dependencias, ttl: timedelta = TTL_PROCESSANDO):
        self.d = deps
        self.ttl = ttl
        if self.d.executor is None:
            self.d.executor = ExecutorThread(self.processar)

    # ------------------------------------------------------------ iniciar
    def iniciar(self, uuid_atendimento: str, id_empresa: int, id_usuario: int, eh_medico: bool):
        if not eh_medico:
            raise PermissaoNegadaError("Somente médico usa a avaliação do Bion.")
        at = self.d.atendimentos.buscar_por_uuid(uuid_atendimento, id_empresa)   # 404 se de outra empresa
        if at.realizado_por != id_usuario:
            raise PermissaoNegadaError("Só o profissional do atendimento pode pedir a avaliação do Bion.")
        if at.tipo_atendimento not in TIPOS_COM_BION:
            raise ConflictoError("A avaliação do Bion só está disponível na avaliação médica e na reavaliação.")
        if at.status != "em-andamento":
            raise ConflictoError("A avaliação do Bion exige atendimento em andamento.")
        self.d.consultas.exigir_consentimento(at.consulta)         # pode ter mudado desde a abertura
        if self.d.inputs_protocolo.find_ultimo_do_atendimento(at.id) is None:
            raise ConflictoError(
                "Registre o input de protocolo deste atendimento antes de pedir a avaliação do Bion.")

        # Serializa cliques simultaneos: trava o atendimento ate o commit da criacao.
        self.d.atendimentos.repo.travar(at)
        self.d.outputs.expirar_travados(at.id, datetime.now(timezone.utc) - self.ttl)
        if self.d.outputs.em_processamento(at.id):
            raise ConflictoError("Já existe uma avaliação do Bion em andamento para este atendimento.")

        config = Config.de_dict(self._config_usuario(id_usuario))
        entrada = InputModel.de_atendimento(at, config)
        out = self.d.outputs.criar(at.id, colunas_envio(entrada))       # commit: o envio fica registrado
        tarefa = Tarefa(id_output=out.id, uuid_output=out.uuid, uuid_atendimento=at.uuid, id_atendimento=at.id,
                        id_usuario=id_usuario, id_empresa=id_empresa, idioma=config.idioma,
                        uuids_em_uso=tuple(self._uuids_em_uso(at)))
        try:
            self.d.executor.enfileirar(tarefa)
        except Exception:
            log.exception("nao foi possivel enfileirar a avaliacao %s", out.uuid)
            self.d.outputs.marcar(out, FALHOU, FILA_INDISPONIVEL)
            raise
        return out

    def _config_usuario(self, id_usuario: int) -> dict | None:
        try:
            return self.d.configuracoes.buscar_por_usuario(id_usuario).to_dict()
        except RecursoNaoEncontradoError:
            return None          # sem configuracao: idioma padrao

    @staticmethod
    def _uuids_em_uso(at) -> list[str]:
        return [m.catalogo_medicamentos.uuid for m in at.consulta.paciente.medicamentos_em_uso
                if m.ativo and m.catalogo_medicamentos is not None]

    # ----------------------------------------------------------- processar
    def processar(self, tarefa: Tarefa) -> None:
        out = self.d.outputs.find_by_id(tarefa.id_output)
        if out is None or out.status != PROCESSANDO:
            return                                         # ja tratada (ou expirada)
        pool = self.d.criar_pool(tarefa)
        try:
            av = avaliar(out.input_ia_json, pool, self.d.cliente)
        except Exception:
            log.exception("erro inesperado na avaliacao %s", tarefa.uuid_output)
            self.d.outputs.marcar(out, FALHOU, INTERNO, pool.colunas())
            return
        if not av.ok:
            self.d.outputs.marcar(out, FALHOU, av.erro_codigo,
                                  {**pool.colunas(), "versao_modelo_ia": av.versao_modelo})
            return

        # 1) o que a IA respondeu e gravado ANTES de agir sobre isso
        self.d.outputs.gravar_resposta(out, {**colunas_resposta(av.output, av.versao_modelo), **pool.colunas()})
        # 2) rascunho
        try:
            resultado = self.d.prescricao_ia.registrar_proposta(
                tarefa.uuid_atendimento, av.output.proposta, tarefa.id_usuario, out.id)
        except Exception:
            log.exception("falha ao registrar a proposta da avaliacao %s", tarefa.uuid_output)
            self.d.outputs.marcar(out, FALHOU, REGISTRO_PROPOSTA)
            return
        # 3) substitui os rascunhos antigos da IA (so quando nasceu um novo)
        if resultado is not None:
            try:
                self._substituir_antigos(tarefa.id_atendimento, resultado.id)
            except Exception:
                log.exception("falha ao substituir rascunhos antigos (%s)", tarefa.uuid_output)
        self.d.outputs.marcar(out, CONCLUIDO)

    def _substituir_antigos(self, id_atendimento: int, id_novo: int) -> None:
        """Remove rascunhos antigos da IA que o medico NAO mexeu (todos os itens com
        origem 'bion_ia'). Se o medico acrescentou item proprio, o rascunho e mantido."""
        antigos = self.d.resultados.rascunhos_ia(id_atendimento, id_novo)
        intactos = [r for r in antigos
                    if all(i.origem_sugestao == "bion_ia" for i in [*r.prescricoes, *r.prescricoes_exame])]
        if intactos:
            self.d.resultados.excluir(intactos)

    # ----------------------------------------------------------- consultar
    def consultar(self, uuid_output: str, id_empresa: int, id_usuario: int) -> dict:
        out = self.d.outputs.find_por_uuid_da_empresa(uuid_output, id_empresa)
        if out is None:
            raise RecursoNaoEncontradoError(f"Avaliação não encontrada: {uuid_output}")
        if out.atendimento.realizado_por != id_usuario:
            raise PermissaoNegadaError("Só o profissional do atendimento pode ver esta avaliação.")
        base = {"uuid_output": out.uuid, "status": out.status, "erro_codigo": out.erro_codigo,
                "criado_em": out.criado_em.isoformat() if out.criado_em else None}
        if out.status != CONCLUIDO or not out.output_ia_json:
            return base
        output = OutputIA.model_validate(out.output_ia_json)
        resultado = self.d.resultados.de_output(out.id)
        snap = out.input_ia_json or {}
        front = montar_output_front(
            output, resultado.to_dict() if resultado else None,
            indices=snap.get("indices_input"), lacunas=snap.get("faltando"),
            substituida=resultado is None and not output.proposta.sem_recomendacao)
        return {**base, **front}
    
    

class OutputBionService:
    
    def __init__(self):
        self.repo = OutputBionRepository()
        
    def buscar_por_uuid(self, uuid: str):
        """Retorna um OutputBion pelo UUID ou lança RecursoNaoEncontradoError."""
        e = self.repo.find_by_uuid(uuid)
        if not e:
            raise RecursoNaoEncontradoError(f"OutputBion não encontrado: {uuid}")
        return e

    
    # --- B1: Confiança média da IA ---
    def media_confianca(self, id_empresa: int, dias: int = 30):
        return self.repo.media_confianca(id_empresa=id_empresa, dias=dias)
 
    # --- B2: Completude média dos dados de entrada ---
    def media_completude(self, id_empresa: int, dias: int = 30):
        return self.repo.media_completude(id_empresa=id_empresa, dias=dias)
 
    # --- B4: Versão do modelo de IA em uso ---
    def versoes_em_uso(self, id_empresa: int, dias: int = 30):
        return self.repo.versoes_em_uso(id_empresa=id_empresa, dias=dias)
 
    # --- E3: pares completude/confiança para correlação ---
    def pares_completude_confianca(self, id_empresa: int, dias: int = 30):
        return self.repo.pares_completude_confianca(id_empresa=id_empresa, dias=dias)

        # --- C5: Queixas principais mais frequentes ---
    def queixas_recentes(self, id_empresa: int, dias: int = 30, limite: int = 200):
        return self.repo.queixas_recentes(id_empresa=id_empresa, dias=dias, limite=limite)
    