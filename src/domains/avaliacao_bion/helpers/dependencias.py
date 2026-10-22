"""Monta as dependencias reais do service. >>> AJUSTE os imports ao seu projeto <<<
(ficam dentro da funcao para o pacote poder ser importado em teste sem o projeto).

inputs_protocolo: InputProtocoloRepository (find_ultimo_do_atendimento). O service
o usa para exigir o input de protocolo antes de iniciar a avaliacao."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.domains.pool_ia import ContextoPool, Pool

from .cliente import ClienteIA, ClienteIAIndisponivel
from .executor import Executor
from .tarefa import Tarefa


@dataclass
class Dependencias:
    atendimentos: object      # AtendimentoService (buscar_por_uuid, repo.travar)
    consultas: object         # ConsultaService (exigir_consentimento)
    configuracoes: object     # modulo/servico com buscar_por_usuario(id_usuario).to_dict()
    prescricao_ia: object     # PrescricaoIAService (registrar_proposta)
    outputs: object           # OutputBionRepository
    resultados: object        # ResultadoRascunhoRepository
    criar_pool: Callable[[Tarefa], Pool]
    cliente: ClienteIA
    inputs_protocolo: object
    executor: Executor | None = None   # definido pelo service se None


def criar_pool(tarefa: Tarefa) -> Pool:
    from src.domains.medicamentos.repository import CatalogoMedicamentosRepository 
    from src.domains.exames.repository import CatalogoExamesRepository               
    from src.domains.exames.conteudo.catalogo_exames_conteudo_repository import CatalogoExamesConteudoRepository
    return Pool(ContextoPool(CatalogoMedicamentosRepository(), CatalogoExamesRepository(),
                             CatalogoExamesConteudoRepository(), idioma=tarefa.idioma,
                             id_empresa=tarefa.id_empresa, id_atendimento=tarefa.id_atendimento,
                             uuids_em_uso=frozenset(tarefa.uuids_em_uso)))


def padrao(cliente: ClienteIA | None = None) -> Dependencias:
    from src.domains.atendimento.service import AtendimentoService                 
    from src.domains.consulta.service import ConsultaService
    from src.domains.configuracao import service as cfg_svc
    from src.domains.prescricao.prescricao_ia_service import PrescricaoIAService
    from ..repository import OutputBionRepository, ResultadoRascunhoRepository
    from src.domains.dados_clinicos.repository import InputProtocoloRepository
    return Dependencias(AtendimentoService(), ConsultaService(), cfg_svc, PrescricaoIAService(),
                        OutputBionRepository(), ResultadoRascunhoRepository(), criar_pool,
                        cliente or ClienteIAIndisponivel(), InputProtocoloRepository())
