"""Acesso a dados da avaliacao Bion (OutputBion e rascunhos da IA)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from realtime import List

from .helpers.modelos import Atendimento, Consulta, OutputBion, ResultadoPrescricao, db

from .helpers.status import EXPIRADO, FALHOU, PROCESSANDO


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class OutputBionRepository:

    def criar(self, id_atendimento: int, colunas: dict) -> OutputBion:
        """Cria a linha do envio (status=processando) e COMMITA: o envio fica
        registrado mesmo que a avaliacao falhe depois."""
        o = OutputBion(id_atendimento=id_atendimento, status=PROCESSANDO, **colunas)
        db.session.add(o)
        db.session.commit()
        return o

    def find_by_id(self, id: int) -> Optional[OutputBion]:
        """Busca um OutputBion pelo ID interno (chave primária)."""
        return db.session.get(OutputBion, id)

    def find_by_uuid(self, uuid: str) -> Optional[OutputBion]:
        """Busca um OutputBion pelo UUID público exposto na API."""
        return OutputBion.query.filter_by(uuid=uuid).first()

    def find_por_uuid_da_empresa(self, uuid: str, id_empresa: int) -> Optional[OutputBion]:
        """A posse vem da Consulta; 'nao existe' e 'e de outra empresa' dao o mesmo None."""
        return (OutputBion.query
                .join(Atendimento, OutputBion.id_atendimento == Atendimento.id)
                .join(Consulta, Atendimento.id_consulta == Consulta.id)
                .filter(OutputBion.uuid == uuid, Consulta.id_empresa == id_empresa)
                .first())

    def em_processamento(self, id_atendimento: int) -> bool:
        return db.session.query(OutputBion.id).filter(
            OutputBion.id_atendimento == id_atendimento, OutputBion.status == PROCESSANDO).first() is not None

    def expirar_travados(self, id_atendimento: int, antes_de: datetime) -> int:
        """'processando' parado desde antes de `antes_de` (servidor reiniciou, tarefa perdida)
        vira 'falhou'/'expirado'. Sem commit: roda dentro da transacao de quem chama."""
        n = (OutputBion.query
             .filter(OutputBion.id_atendimento == id_atendimento, OutputBion.status == PROCESSANDO,
                     OutputBion.criado_em < antes_de)
             .update({"status": FALHOU, "erro_codigo": EXPIRADO, "concluido_em": _agora()},
                     synchronize_session=False))
        db.session.flush()
        return n

    def gravar_resposta(self, o: OutputBion, colunas: dict) -> None:
        """Grava o que a IA respondeu (status continua 'processando' ate registrar a proposta)."""
        for k, v in colunas.items():
            setattr(o, k, v)
        db.session.commit()

    def marcar(self, o: OutputBion, status: str, erro_codigo: str | None = None,
               colunas: dict | None = None) -> None:
        for k, v in (colunas or {}).items():
            setattr(o, k, v)
        o.status = status
        o.erro_codigo = erro_codigo
        o.concluido_em = _agora()
        db.session.commit()


    def _query_filtrada_empresa(self, id_empresa: int, dias: int):
        """Monta a base de query com os 4 joins até Usuario, reaproveitada
        por B1, B2 e B4 -- evita repetir o mesmo caminho 3 vezes.
 
        Caminho: OutputBion -> InputProtocolo -> ColetaClinica ->
        Atendimento -> realizado_por -> Usuario.
        """
        from datetime import datetime, timedelta, timezone
        from src.models.usuarios import Usuario
        from src.models.clinico import ColetaClinica, Atendimento, InputProtocolo
 
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
 
        return (
            db.session.query(OutputBion)
            .join(Atendimento, OutputBion.id_atendimento == Atendimento.id)
            .join(ColetaClinica, InputProtocolo.id_coleta_clinica == ColetaClinica.id)
            .join(Atendimento, ColetaClinica.id_atendimento == Atendimento.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(OutputBion.criado_em >= limite)
        )
 
    # --- B1: Confiança média da IA ---
    def media_confianca(self, id_empresa: int, dias: int = 30) -> Optional[float]:
        """Média de indice_confianca no período. None se não houver dados."""
        from sqlalchemy import func
 
        media = (
            self._query_filtrada_empresa(id_empresa, dias)
            .with_entities(func.avg(OutputBion.indice_confianca))
            .scalar()
        )
        return float(media) if media is not None else None
 
    # --- B2: Completude média dos dados de entrada ---
    def media_completude(self, id_empresa: int, dias: int = 30) -> Optional[float]:
        """Média de indice_completude no período. None se não houver dados."""
        from sqlalchemy import func
 
        media = (
            self._query_filtrada_empresa(id_empresa, dias)
            .with_entities(func.avg(OutputBion.indice_completude))
            .scalar()
        )
        return float(media) if media is not None else None
 
    # --- B4: Versão do modelo de IA em uso ---
    def versoes_em_uso(self, id_empresa: int, dias: int = 30) -> List[dict]:
        """Contagem de outputs por versao_modelo_ia no período -- útil
        pra saber se ainda existem execuções em versão antiga durante
        um rollout gradual.
 
        Retorna: [{"versao_modelo_ia": "v2.3.1", "total": 140}, ...]
        """
        from sqlalchemy import func
 
        linhas = (
            self._query_filtrada_empresa(id_empresa, dias)
            .with_entities(
                OutputBion.versao_modelo_ia.label("versao"),
                func.count(OutputBion.id).label("total"),
            )
            .group_by(OutputBion.versao_modelo_ia)
            .order_by(func.count(OutputBion.id).desc())
            .all()
        )
        return [{"versao_modelo_ia": linha.versao, "total": linha.total} for linha in linhas]
 
    # --- E3: pares (completude, confianca) para correlação ---
    def pares_completude_confianca(self, id_empresa: int, dias: int = 30) -> list:
        """Lista de tuplas (indice_completude, indice_confianca) dos
        outputs no período, só os que têm AMBOS os valores preenchidos
        -- correlação não faz sentido com par incompleto.
        """
        linhas = (
            self._query_filtrada_empresa(id_empresa, dias)
            .filter(OutputBion.indice_completude.isnot(None))
            .filter(OutputBion.indice_confianca.isnot(None))
            .with_entities(OutputBion.indice_completude, OutputBion.indice_confianca)
            .all()
        )
        return [(float(c), float(cf)) for c, cf in linhas]
    
    # --- C5: Queixas principais mais frequentes ---
    def queixas_recentes(self, id_empresa: int, dias: int = 30, limite: int = 200) -> List[str]:
        """Lista bruta de queixa_principal (texto livre) no período,
        filtrado por empresa.
 
        Texto livre não agrupa direto em SQL (GROUP BY teria N grupos
        de 1 linha cada, já que a escrita varia). Este método devolve
        a lista crua; a camada de estatística é quem faz a normalização
        (lowercase, tokenização simples) e conta frequência de termos --
        não é um ranking exato de frases, é aproximado por natureza.
 
        Limitado a `limite` registros mais recentes por padrão, pra não
        carregar uma tabela inteira de texto na memória sem necessidade.
        """
        from datetime import datetime, timedelta, timezone
        from src.models.usuarios import Usuario
        from src.models.clinico import ColetaClinica, Atendimento
        from src.models.clinico import InputProtocolo
        
        limite_data = datetime.now(timezone.utc) - timedelta(days=dias)
 
        linhas = (
            db.session.query(InputProtocolo.queixa_principal)
            .join(ColetaClinica, InputProtocolo.id_coleta_clinica == ColetaClinica.id)
            .join(Atendimento, ColetaClinica.id_atendimento == Atendimento.id)
            .join(Usuario, Atendimento.realizado_por == Usuario.id)
            .filter(Usuario.id_empresa == id_empresa)
            .filter(Atendimento.data_hora_inicio >= limite_data)
            .filter(InputProtocolo.queixa_principal.isnot(None))
            .order_by(Atendimento.data_hora_inicio.desc())
            .limit(limite)
            .all()
        )
        return [linha[0] for linha in linhas if linha[0] and linha[0].strip()]
    
    
    
class ResultadoRascunhoRepository:

    def de_output(self, id_output: int) -> Optional[ResultadoPrescricao]:
        return ResultadoPrescricao.query.filter_by(id_output=id_output).first()

    def rascunhos_ia(self, id_atendimento: int, exceto_id: int) -> list[ResultadoPrescricao]:
        """Rascunhos que vieram da IA (id_output preenchido) neste atendimento, menos o novo."""
        return (ResultadoPrescricao.query
                .filter(ResultadoPrescricao.id_atendimento == id_atendimento,
                        ResultadoPrescricao.status == "rascunho",
                        ResultadoPrescricao.id_output.isnot(None),
                        ResultadoPrescricao.id != exceto_id)
                .all())

    def excluir(self, resultados: list[ResultadoPrescricao]) -> None:
        """O cascade do model leva medicamentos e exames junto."""
        for r in resultados:
            db.session.delete(r)
        db.session.commit()


    
    