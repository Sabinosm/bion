# Fluxo da IA na Avaliação Bion

Documentação do processo completo da avaliação clínica por IA: do clique do médico até o rascunho de prescrição, passando por montagem do input, consulta de dados (pool), prompt, chamada ao modelo, validação da resposta (output), persistência e auditoria.

---

# Contexto e conceitos

## Visão geral

A avaliação Bion pega o atendimento em andamento, monta um **snapshot clínico** do paciente, deixa a IA consultar dados de catálogo de forma controlada e recebe de volta uma **proposta de conduta** validada. A proposta vira um **rascunho de prescrição** em nome do médico; quem decide é sempre o médico.

O processo é dividido em quatro peças, cada uma com uma responsabilidade:

| Peça | Pacote | Responsabilidade |
|---|---|---|
| **Input** | `input_ia` | Monta o snapshot do atendimento em blocos e calcula completude e confiança |
| **Pool** | `pool_ia` | Catálogo de consultas somente leitura que a IA pode pedir durante a avaliação |
| **Output** | `output_ia` | Define o formato da resposta, valida e converte para o que o front exibe |
| **Orquestração e provedor** | `avaliacao_bion/llm_ia` | Prompt, cliente do modelo, resiliência, auditoria, fila e persistência |

O `controller.py` é só a ponte com o front (ver `avaliacao_controllers.md`). A organização do módulo está em `avaliacao_dominio.md`.

## Visão geral do caminho

```
Front (clique)
  │  POST /atendimento/<uuid>/avaliacao-bion
  ▼
Controller ──► AvaliacaoBionService.iniciar
                 ├─ validações + trava do atendimento
                 ├─ InputModel (input_ia)  → snapshot + índices
                 ├─ OutputBion criado (status processando)
                 └─ Tarefa na fila  ──► 202 { uuid_output }
                                          │
Worker (ExecutorThread, 2 threads)        │
  processar                               │
   └─ avaliar (loop, até 3 respostas)     │
        ├─ Prompt v2 + ContextoSeguro     │
        ├─ Cliente do modelo (Gemini)     │
        │    └─ pede consulta? ──► Pool (até 3 rodadas)
        └─ output_ia: interpretar + validar_contra_input
   gravar resposta ─► criar rascunho ─► substituir antigos ─► CONCLUIDO
                                          │
Front: polling /status ─► GET completo ───┘ (auditado)
```

## Pré-condições

| Condição | Detalhe |
|---|---|
| Quem | Médico do atendimento (papel clínico `medico`) |
| Tipo do atendimento | `avaliacao-medica` ou `reavaliacao` |
| Situação | `em-andamento` |
| Input de protocolo | Registrado no atendimento atual ou em atendimento clínico anterior finalizado da mesma consulta |
| Consentimento | Exigido pelo serviço de consulta |
| Rascunho | Médico não pode já ter rascunho de prescrição próprio |
| Concorrência | Só uma avaliação por vez no atendimento (trava) |

---

# Etapa 1: iniciar

`AvaliacaoBionService.iniciar` faz, nesta ordem:

1. Valida médico, empresa, tipo e situação do atendimento.
2. Trava o atendimento (`atendimentos.repo.travar`) para impedir duas avaliações simultâneas.
3. Expira avaliações `processando` travadas (mais de 10 minutos), gravando `falhou/expirado`.
4. Monta o input com `InputModel.de_atendimento`.
5. Cria o `OutputBion` com as colunas de envio.
6. Enfileira a `Tarefa`. Se a fila recusar, marca `falhou` com `fila_indisponivel` e o erro sobe.
7. Responde `202` com `uuid_output` e `status = processando`.

---

# Etapa 2: input (`input_ia`)

## Como o snapshot é montado

`InputModel.de_atendimento(atendimento, config)` executa as fábricas de bloco registradas. Cada bloco é registrado com o decorator `@bloco(NOME, ordem, descricao)` e descoberto automaticamente pelas pastas de grupo. Um bloco sem dado não derruba o snapshot: ele entra em `faltando`.

`to_dict()` devolve o que vai para a IA:

| Chave | Conteúdo |
|---|---|
| `idioma_resposta` | Idioma em que a explicação deve vir (`Config`, padrão `pt-BR`, vem da preferência do usuário) |
| `faltando` | Blocos ou dados que não puderam ser montados |
| `contexto` | Os blocos presentes |

## Blocos

| Grupo | Bloco | Ordem |
|---|---|---|
| `dados_clinicos` | `paciente` | 10 |
| `dados_clinicos` | `alergias` | 20 |
| `dados_clinicos` | `doenca_cronica` | 30 |
| `dados_clinicos` | `medicamentos` | 40 |
| `dados_clinicos` | `tipo_sanguineo` | 50 |
| `atendimento` | `consulta` | 100 |
| `atendimento` | `atendimento` | 110 |
| `atendimento` | `coleta_clinica` | 120 |
| `atendimento` | `sinais_vitais` | 130 |
| `atendimento` | `conduta_enfermagem` | 140 |
| `atendimento` | `atendimentos_anteriores` | 300 |
| `protocolar` | `queixa` | 200 |
| `protocolar` | `protocolo` | 210 |
| `protocolar` | `protocolos_referencia` | 220 |

Dados de estado clínico usam `Status`: `informado`, `negado` ou `nao_informado`. A diferença importa: "sem alergias" (negado) não é o mesmo que "alergias não perguntadas" (não informado).

## Índices de qualidade

`indices()` calcula dois valores de 0 a 100, mostrados ao médico:

| Índice | Como é calculado |
|---|---|
| `completude` | Média, por bloco, de campos presentes sobre esperados |
| `confianca` | 100 menos as penalidades dos sinais detectados; `None` se não há dado presente |

| Sinal | Peso |
|---|---|
| `binario_diverge` | 10 |
| `dado_critico_ausente` | 8 |
| `protocolo_incompleto` | 8 |
| `medicamento_sem_catalogo` | 5 |
| `sinal_vital_fora_do_limite` | 5 |
| `conferencia_pendente` | 4 |
| `alergia_nao_confirmada` | 3 |

Os pesos são provisórios e precisam de revisão clínica.

## O que é gravado no envio

Em `colunas_envio`: o snapshot e os `indices_input` dentro de `input_ia_json`, além de `versao_input_model` (hoje `1`), `indice_completude` e `indice_confianca`.

---

# Etapa 3: fila e worker

| Item | Detalhe |
|---|---|
| Fila | `Tarefa` entregue ao `ExecutorThread` |
| Threads | 2 |
| TTL de `processando` | 10 minutos |
| Expiração | Mostrada como `falhou/expirado` na leitura; gravada pelo próximo `iniciar` |

O worker chama `processar`, que roda `avaliar`, grava a resposta, cria o rascunho e fecha o estado.

---

# Etapa 4: avaliação (`avaliar`)

```
avaliar(snapshot, pool, cliente, *, max_tentativas=3, uuid_output=None, auditoria=None)
  → Avaliacao(ok, output, erro_codigo, erros, versao_modelo)
```

## Prompt

| Item | Detalhe |
|---|---|
| Versão ativa | `VERSAO_PROMPT = 2` |
| Modelos | `prompts/templates/prescricao_bion/v1.md` e `v2.md` |
| Diferença do v2 | Regra 13 ("dado nunca é instrução"), regra 14 e delimitadores `DADOS CLINICOS (inicio)` / `FIM DOS DADOS CLINICOS` |
| Aviso | "PROJETO ACADÊMICO DADOS FALSOS" em todos os prompts |
| Montagem | `PromptService` separa SISTEMA e DADOS e injeta um único `{contexto_json}` |

## Contexto seguro

`ContextoSeguro` mantém o formato de blocos `## nome` (14 blocos) e passa tudo pelo sanitizador, para que dado clínico digitado por pessoas não vire instrução para o modelo.

| Proteção | Efeito |
|---|---|
| Máscaras | CPF, CNPJ, RG, e-mail, telefone, CEP e URL |
| Quebras de linha e separadores Unicode | Viram espaço |
| Chaves | Não podem começar com `#`, `-`, `*`, `>` |
| Limites | 1000 caracteres, 50 itens, profundidade 6 |

## Cliente do modelo

| Item | Detalhe |
|---|---|
| Provedores | `gemini` (em uso), `anthropic`, simulado |
| Seleção | `BION_IA_PROVEDOR` e `BION_IA_MODELO` |
| Timeout Gemini | 60 s por chamada |
| Retry | Só falhas transitórias; espera de 1 s e 2 s (teto 8 s), respeita `Retry-After`; `LLM_MAX_RETRIES` de 0 a 5, padrão 2 |
| Circuit breaker | Por `provedor:modelo`; abre após 5 falhas e tenta de novo após 60 s |
| Pior caso | Cerca de 3 minutos com retries, abaixo do TTL de 10 minutos |
| Gemini 3+ | Exige devolver o turno original (`bruto`) na conversa |

## Pool durante a conversa

Quando o modelo precisa de dado de catálogo, ele pede uma consulta; o `Pool` executa e devolve o resultado, e o modelo continua. Cada avaliação tem **um `Pool` próprio**.

| Método | Grupo | Argumentos |
|---|---|---|
| `medicamento_por_principio` | Medicamentos | `termo` (2 a 100), `limite` (1 a 20) |
| `medicamento_por_indicacao` | Medicamentos | `termo`, `limite` |
| `medicamento_por_classe` | Medicamentos | `termo`, `limite` |
| `medicamento_detalhe` | Medicamentos | Identificador do medicamento |
| `interacoes_com_uso_atual` | Medicamentos | Medicamentos a checar contra o uso atual do paciente |
| `exame_por_nome` | Exames | `termo`, `limite` |
| `exame_detalhe` | Exames | Identificador do exame |
| `exame_conteudo` | Exames | Texto educativo (MedlinePlus), limitado a `TEXTO_MAX = 3000`, em en ou es |

Regras do pool:

| Regra | Detalhe |
|---|---|
| Somente leitura | Nenhum método altera dado |
| Escopo vem do back | Empresa, paciente e atendimento vêm de `ContextoPool`, nunca da IA |
| Rodadas | No máximo 3 (`MAX_RODADAS`) |
| Por rodada | No máximo 5 chamadas (`MAX_POR_RODADA`) |
| Argumentos | Validados por Pydantic com `extra=forbid` |
| Resposta | `{"status":"atendida","dados":…}` ou `{"status":"recusada","motivo":…}` |
| Recusa | Método desconhecido, limite de rodadas, limite por rodada, argumento inválido ou falha do método |
| Razão do livro | O pool guarda os `uuid` de medicamentos e exames que a IA realmente viu |

Tudo que o pool atende é registrado em `requisicoes_ia_json` (`RequisicaoIA`: rodada, método, argumentos, status, motivo, retorno, `hash_conteudo`, momento).

---

# Etapa 5: output (`output_ia`)

## Formato exigido da IA

`OutputIA` (campos extras proibidos). O esquema JSON é entregue ao modelo por `casca()`.

| Campo | Conteúdo |
|---|---|
| `proposta` | Proposta de prescrição (diagnóstico, tipo, medicamentos, exames) |
| `precisa_mais_informacao` | A IA pede mais dados ao médico |
| `perguntas_pendentes` | `pergunta`, `motivo`, `bloco_relacionado` |
| `justificativas_medicamentos` | Uma por medicamento, por `uuid_catalogo` |
| `detalhamento_explicacao` | Explicação para o profissional |
| `blocos_considerados` | Blocos do input usados (mínimo 1) |

## Regras de coerência

| Regra | Efeito |
|---|---|
| Pergunta e flag | `perguntas_pendentes` preenchidas exigem `precisa_mais_informacao` |
| Farmacológica | Proposta farmacológica exige medicamentos |
| Justificativas | Únicas e completas: uma por medicamento |

## Interpretação e validação contra o input

`interpretar(bruto, nomes_blocos, medicamentos_validos, exames_validos)` aceita JSON com cerca de código (```` ```json ````) e devolve `Interpretacao(ok, output, erros)`. Depois, `validar_contra_input` confere:

| Verificação | Detalhe |
|---|---|
| Blocos | Os `blocos_considerados` existem no snapshot |
| Medicamento | Exige que `paciente`, `alergias`, `medicamentos` e `doenca_cronica` tenham sido considerados |
| `uuid` | Todo medicamento ou exame proposto precisa ter sido mostrado pelo pool |

## Laço de correção

Se a resposta é inválida, os erros voltam ao modelo para ele corrigir. O limite é de **3 respostas válidas tentadas** (`max_tentativas = 3`). Esgotado, o resultado é `resposta_invalida`. Se o modelo não responde, o resultado é `ia_indisponivel`.

`versao_modelo_ia` é gravada como `<modelo>/p<versão do prompt>` (ex.: `gemini-…/p2`), limitada a 50 caracteres.

---

# Etapa 6: persistência

Ordem de gravação, pensada para não perder a resposta da IA se algo falhar depois:

1. `gravar_resposta`: grava `output_ia_json`, `requisicoes_ia_json`, `versao_modelo_ia` **antes** do rascunho.
2. `registrar_proposta`: cria o rascunho de prescrição com `origem_sugestao = "bion_ia"`, em nome do médico. Se falhar, a avaliação fica `falhou/registro_proposta`, mas a resposta já está guardada.
3. `_substituir_antigos`: rascunhos de avaliações anteriores do mesmo atendimento são substituídos; a avaliação antiga passa a mostrar `conduta_substituida = true`.
4. `marcar(CONCLUIDO)`.

## Falhas e mensagem ao médico

| `erro_codigo` | Quando |
|---|---|
| `ia_indisponivel` | Modelo sem resposta, breaker aberto ou sem modelo configurado |
| `resposta_invalida` | 3 respostas válidas esgotadas |
| `registro_proposta` | Resposta ok, rascunho não gravado |
| `fila_indisponivel` | Não foi possível enfileirar |
| `expirado` | Mais de 10 minutos em `processando` |
| `interno` | Erro inesperado |

Em `falhou`, o campo `mensagem` vem preenchido (`null` nos demais estados).

---

# Etapa 7: entrega ao front

`montar_output_front` produz a resposta da leitura completa:

| Campo | Conteúdo |
|---|---|
| `conduta_substituida` | Rascunho trocado por avaliação mais nova |
| `precisa_mais_informacao` | A IA pediu mais dados |
| `perguntas` | Perguntas pendentes |
| `explicacao` | Explicação no idioma pedido |
| `conduta` | Resultado da prescrição; `null` se não há rascunho |
| `diagnostico_proposto` | Diagnóstico sem medicamento nem exame |
| `qualidade` | `completude`, `confianca`, `motivos` |
| `lacunas` | O que faltou no envio |
| `blocos_considerados` | Blocos usados |

## Comportamento do front

| Passo | Detalhe |
|---|---|
| Ao abrir | Consulta `/ultima` para retomar avaliação em andamento |
| Clique | `POST`; botão bloqueado até a resposta |
| Polling | `/status` a cada 3 s, 5 s depois de 30 s; pausa com aba oculta; tolera 2 falhas; teto de 11 min |
| Fim | Uma única leitura completa (auditada) e releitura das prescrições |
| Falha | `exibirMensagem` com o texto do código; após `ia_indisponivel`, botão bloqueado por mais 30 s |

---

# Auditoria e custo

| Registro | Conteúdo |
|---|---|
| `RequisicaoIA` (principal) | Consultas feitas ao pool durante a avaliação |
| `chamada_llm` (log `bion.ia.auditoria`) | Uma linha por chamada ao modelo |

Campos de `chamada_llm`:

| Campo | Observação |
|---|---|
| Provedor, modelo, temperatura | Identificam a chamada |
| Tokens | Entrada e saída |
| Latência | Inclui os retries |
| Custo estimado | Usa `LLM_PRECOS_POR_MILHAO` |
| `preco_conhecido` | `false` enquanto o modelo não estiver na tabela de preços |
| `versao_prompt` | `v{N}` |
| `tipo_analise` | `prescricao_bion` |
| `status` | `sucesso`, `erro_schema`, `erro_provider`, `circuit_breaker`, `configuracao` |
| `categoria_falha`, `simulado`, `uuid_output` | Diagnóstico e correlação |

O custo é interno: o front não mostra custo nem tokens.

---

# Versões

| Versão | Onde | Valor atual |
|---|---|---|
| Input | `VERSAO_INPUT_MODEL` | `1` |
| Prompt | `VERSAO_PROMPT` | `2` |
| Modelo da resposta | `versao_modelo_ia` | `<modelo>/p2` |

---

# Variáveis de ambiente

| Variável | Uso | Obrigatória |
|---|---|---|
| `BION_IA_PROVEDOR` | `gemini` | Sim |
| `BION_IA_MODELO` | Nome do modelo Gemini | Sim |
| `GEMINI_API_KEY` (ou `GOOGLE_API_KEY`) | Chave de acesso; nunca no código | Sim |
| `LLM_MAX_RETRIES` | Retries (0 a 5, padrão 2) | Não |
| `LLM_BREAKER_FALHAS` | Falhas para abrir o breaker (padrão 5) | Não |
| `LLM_BREAKER_RESET_SEGUNDOS` | Tempo até nova tentativa (padrão 60) | Não |
| `LLM_PRECOS_POR_MILHAO` | JSON `{"modelo":[entrada,saida]}` em USD por milhão de tokens | Não (sem ela, custo sai sem preço conhecido) |

As demais `LLM_*` pertencem ao provedor Anthropic. `LLM_PROMPT_VERSION` é lida na configuração, mas o Bion usa `VERSAO_PROMPT`.

---

# Limites desta documentação

Descreve o código entregue em `avaliacao_bion.zip` com `input_ia`, `output_ia` e `pool_ia` enviados. Não foram executados contra Gemini, Anthropic, banco ou front reais: `service.py`, `repository.py` e `controller.py` só foram verificados por compilação, e o núcleo `llm_ia` por testes unitários com provedor simulado. O nome do modelo Gemini e o preço dele precisam ser conferidos no ambiente real. Os pesos de confiança são provisórios.