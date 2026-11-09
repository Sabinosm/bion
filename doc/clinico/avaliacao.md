# Domínio da Avaliação Bion

Documentação do módulo `avaliacao_bion`: sua estrutura, o ciclo de vida de uma avaliação (`OutputBion`), as regras de negócio, a persistência, a fila, as métricas e a configuração.

---

# Contexto e conceitos

## Visão geral

O módulo reúne, em uma pasta única, tudo o que lida com a avaliação clínica por IA. Ele tem duas responsabilidades separadas por subpasta:

| Parte | Responsabilidade |
|---|---|
| `avaliacao_bion/` (raiz) | Ponte com o front: `controller.py` e o contrato público em `__init__.py` |
| `avaliacao_bion/llm_ia/` | Núcleo de IA: laço com o modelo, prompt versionado, contexto seguro, provedores, resiliência e auditoria |
| `avaliacao_bion/llm_ia/fluxo/` | Fluxo e persistência: serviço, repositório, tarefa, fila, status e dependências |

O módulo usa três pacotes de serviço da IA, que só ele consome: `input_ia` (monta o que a IA recebe), `pool_ia` (as ferramentas de consulta) e `output_ia` (valida o que a IA devolve). O antigo `protocolos_ia` foi removido.

Regras de dependência, verificadas por teste:

| Parte | Pode importar | Não pode importar |
|---|---|---|
| Núcleo (`llm_ia` fora de `fluxo`) | `input_ia`, `output_ia`, `pool_ia`, biblioteca padrão | `controller`, `fluxo`, Flask, `src.models`, `protocolos_ia` |
| `fluxo` | Núcleo, `src.models`, repositórios e serviços do host | `protocolos_ia`, `dados_clinicos.envio_ia_service` |

Por isso o núcleo roda e é testado sem banco e sem servidor.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `controller.py` | Rotas (ver `avaliacao_controllers.md`) |
| `__init__.py` | Exporta o laço, o resultado, o contrato do cliente de IA e `Tarefa`; o blueprint é carregado sob demanda |
| `llm_ia/avaliador.py` | Laço de turnos com o modelo, ferramentas, validação e nova tentativa |
| `llm_ia/prompts/` | Serviço de prompt, prompt de prescrição e templates `v1.md` e `v2.md` |
| `llm_ia/contexto/` | Contexto clínico seguro: renderiza e sanitiza o snapshot |
| `llm_ia/cliente.py`, `fabrica.py`, `provedores/` | Contrato do cliente de IA, escolha do provedor e implementações (Gemini, Anthropic, simulado) |
| `llm_ia/resilience.py`, `circuit_breaker.py`, `exceptions.py`, `config.py` | Nova tentativa, breaker, taxonomia de erros e configuração |
| `llm_ia/auditoria.py`, `auditoria_operacional.py`, `cost_calculator.py` | Registro de provedor, modelo, tokens, tempo e custo por chamada |
| `llm_ia/sanitizer.py`, `codigos.py`, `raw_response.py` | Máscara de identificadores, códigos de erro da IA e resposta bruta do provedor |
| `llm_ia/fluxo/service.py` | Regras de negócio e fluxo assíncrono |
| `llm_ia/fluxo/repository.py` | Acesso a `OutputBion` e aos resultados de prescrição |
| `llm_ia/fluxo/tarefa.py`, `executor.py` | O que o worker recebe e quem o executa |
| `llm_ia/fluxo/dependencias.py` | Monta o serviço com repositórios, cliente de IA e pool |
| `llm_ia/fluxo/status.py` | Estados, códigos de erro e mensagens ao médico |
| `llm_ia/fluxo/modelos.py` | Reexporta os modelos do banco usados pelo repositório |

---

# Regras de negócio

| Regra | Efeito |
|---|---|
| Só o médico usa a IA | Outro papel recebe `403` |
| Só o profissional do atendimento | `403` para outro médico |
| Tipos permitidos: `avaliacao-medica` e `reavaliacao` | Outro tipo recebe `409` |
| Atendimento `em-andamento` | Outro estado recebe `409` |
| Consentimento da consulta | Revalidado no início, porque pode ter mudado desde a abertura |
| Input de protocolo | Exigido no atendimento atual ou em clínico anterior finalizado da mesma consulta; etapas canceladas ou em andamento não contam |
| Uma avaliação por vez | Há uma trava no atendimento até o commit, para cliques simultâneos não criarem duas |
| Rascunho do médico | Se existe rascunho com item do próprio médico, a IA não gera outra avaliação (`409`) |
| Substituição de rascunhos da IA | Um novo rascunho remove os antigos da IA em que todos os itens têm origem `bion_ia`; se o médico acrescentou item próprio, o rascunho é mantido |
| Sem prescrição automática | O resultado é sempre rascunho; quem decide é o médico |

---

# Ciclo de vida de `OutputBion`

Uma linha por envio, criada antes da chamada à IA.

| Fase | Colunas gravadas |
|---|---|
| Envio (`iniciar`) | `status = processando`, `input_ia_json` (snapshot congelado mais `indices_input`), `versao_input_model`, `indice_completude`, `indice_confianca` |
| Resposta válida | `output_ia_json`, `versao_modelo_ia`, `requisicoes_ia_json` (auditoria das ferramentas) e `status = concluido` |
| Falha | `status = falhou`, `erro_codigo`; mantém `requisicoes_ia_json` e, quando há, `versao_modelo_ia` |

| Transição | Quando |
|---|---|
| `processando → concluido` | Resposta válida e rascunho gravado |
| `processando → falhou` | Qualquer falha listada abaixo |
| `processando → falhou (expirado)` | Mais de 10 minutos em `processando`; gravado no próximo `iniciar` e mostrado na leitura |

| `erro_codigo` | Origem |
|---|---|
| `ia_indisponivel`, `resposta_invalida` | Núcleo de IA (definidos em `llm_ia/codigos.py`) |
| `registro_proposta` | Falha ao gravar o rascunho |
| `fila_indisponivel` | Falha ao enfileirar |
| `expirado` | TTL de `processando` |
| `interno` | Erro inesperado em `processar` |

Ordem de gravação em `processar`:

1. Grava a resposta da IA **antes** de agir sobre ela.
2. Registra o rascunho de prescrição com `origem_sugestao = bion_ia`.
3. Se nasceu um rascunho novo, remove os antigos da IA que o médico não alterou.
4. Marca `concluido`.

## Versões registradas

| Versão | Onde | Valor atual |
|---|---|---|
| Formato do input | `versao_input_model` | `1` |
| Prompt | Constante `VERSAO_PROMPT` em `llm_ia/prompts/prescricao.py` | `2` |
| Modelo e prompt | `versao_modelo_ia` | `<versão devolvida pelo provedor ou do cliente>/p<VERSAO_PROMPT>`, cortado em 50 caracteres |

O prompt `v2` está ativo no código entregue. Ele mantém as regras do `v1` e acrescenta que o conteúdo dos dados é sempre informação, nunca instrução, e que o bloco de dados termina só em `FIM DOS DADOS CLINICOS`.

---

# Fila e processamento

| Item | Comportamento |
|---|---|
| `Tarefa` | Só tipos simples e serializáveis em JSON (ids, uuids, idioma, medicamentos em uso), para trocar a thread por uma fila externa sem mexer no resto |
| `ExecutorThread` | Pool de 2 threads dentro do processo Flask |
| Reinício do servidor | A tarefa em andamento se perde; o `processando` expira pelo TTL de 10 min e vira `falhou/expirado` |
| Idempotência | `processar` ignora uma tarefa cuja avaliação já não está `processando` |

Para produção pesada, basta implementar o contrato de executor com uma fila real e chamar `service.processar(tarefa)`.

---

# Serviços e repositórios

## `AvaliacaoBionService`

| Método | Função |
|---|---|
| `iniciar` | Valida as regras, trava, cria `OutputBion`, enfileira |
| `processar` | Roda no worker: laço com a IA, gravação da resposta, rascunho e troca dos antigos |
| `status` | Estado para o polling |
| `ultima` | Estado da avaliação mais recente do atendimento |
| `consultar` | Conteúdo da avaliação concluída, com `output_front` remontado |

## `OutputBionService` (métricas por empresa)

Todas recebem `id_empresa` e `dias` (padrão 30). Os nomes e retornos não mudaram.

| Método | Retorno |
|---|---|
| `buscar_por_uuid(uuid)` | `OutputBion`, ou `RecursoNaoEncontradoError` |
| `media_confianca` | Confiança média do input |
| `media_completude` | Completude média do input |
| `versoes_em_uso` | Versões de modelo em uso |
| `pares_completude_confianca` | Pares para correlação |
| `queixas_recentes(limite=200)` | Queixas mais frequentes |

## `OutputBionRepository`

| Método | Função |
|---|---|
| `criar`, `find_by_id`, `find_by_uuid`, `find_por_uuid_da_empresa` | Criação e busca, esta última restrita à empresa |
| `ultimo_do_atendimento`, `em_processamento` | Apoio ao polling e à trava de concorrência |
| `expirar_travados` | Marca como `falhou/expirado` o que passou do TTL |
| `gravar_resposta`, `marcar` | Escrita da resposta e dos estados de falha |
| Consultas de métricas | Base do `OutputBionService` |

`ResultadoRascunhoRepository` oferece `de_output`, `rascunhos_ia`, `tem_rascunho_do_medico` e `excluir`, usados na regra de substituição de rascunhos.

---

# Configuração

Para usar o Gemini bastam três variáveis de ambiente:

| Variável | Valor | Se faltar |
|---|---|---|
| `BION_IA_PROVEDOR` | `gemini` | O padrão é `indisponivel`; toda avaliação termina como `ia_indisponivel` |
| `BION_IA_MODELO` | Nome do modelo | Erro de configuração |
| `GEMINI_API_KEY` | Chave (ou `GOOGLE_API_KEY`) | Erro de configuração |

Opcionais:

| Variável | Uso | Padrão |
|---|---|---|
| `LLM_MAX_RETRIES` | Novas tentativas, de 0 a 5 | 2 |
| `LLM_BREAKER_FALHAS` | Falhas seguidas para abrir o breaker | 5 |
| `LLM_BREAKER_RESET_SEGUNDOS` | Tempo até testar de novo | 60 |
| `LLM_PRECOS_POR_MILHAO` | JSON `{"modelo": [entrada, saída]}` em USD por milhão de tokens; sem ele, o custo do Gemini sai estimado | tabela do código, sem preço do Gemini |

As variáveis `LLM_*` restantes são da Anthropic. Chaves só vêm de variável de ambiente.

O timeout do Gemini é `timeout_s`, hoje **60 s** no código entregue. No pior caso, 3 tentativas mais as esperas somam cerca de 3 minutos, dentro do TTL de 10 minutos.

---

# Mudanças em relação à versão anterior

| Ponto | Antes | Agora |
|---|---|---|
| Estrutura | Controller, service, repository e helpers na raiz; dependência do `protocolos_ia` | Controller na raiz; núcleo e fluxo em `llm_ia/` |
| Chamada ao modelo | Uma tentativa | Nova tentativa só em falha transitória, breaker, erros classificados |
| Prompt | Texto fixo no código | Templates versionados; `v2` ativo |
| Contexto | Quebra de linha em texto livre podia forjar um bloco | Quebras e chaves neutralizadas |
| Auditoria | Só `RequisicaoIA` | `RequisicaoIA` mais tempo, tokens e custo por chamada |
| Falha ao médico | `erro_codigo` | `erro_codigo` mais `mensagem` |

Não mudaram: contrato de entrada e saída, colunas de `OutputBion`, polling, `montar_output_front`, rascunho com `origem_sugestao = bion_ia` e auditoria `RequisicaoIA`.

---

# Pontos de atenção

| Ponto | Detalhe |
|---|---|
| Pasta `helpers/` no zip | `avaliacao_bion.zip` ainda traz `avaliacao_bion/helpers/` com os arquivos originais (avaliador, cliente, fabrica, provedores, prompt etc.). Nada do módulo atual a importa, e o `helpers/avaliador.py` ainda importa o `protocolos_ia`, já removido. Se ficou por engano, pode ser apagada |
| Importações do host | Qualquer import fora deste módulo dos caminhos antigos (`avaliacao_bion.service`, `.repository`, `.helpers.*`) precisa apontar para `avaliacao_bion.llm_ia.fluxo` |
| Custo do Gemini | Sem `LLM_PRECOS_POR_MILHAO`, sai com preço de reserva e `preco_conhecido = false` |
| Tokens de tentativas que falharam | Não são contados |
| Verificação | O núcleo é testado com clientes e SDK falsos. `fluxo` e `controller` só foram compilados; nada foi executado contra Gemini, Anthropic ou banco reais |