# Controllers da Avaliação Bion

Documentação das rotas HTTP da avaliação clínica por IA (Bion): quem pode chamar, o que cada rota recebe e devolve, quais erros podem sair e como o front as consome.

---

# Contexto e conceitos

## Visão geral

O `controller.py` do `avaliacao_bion` é a **ponte com o front**. Ele não conhece IA, prompt nem banco: recebe a requisição, pega empresa, usuário e função clínica da sessão, delega ao `AvaliacaoBionService` e traduz o resultado ou a exceção em JSON. Todo o processamento de IA fica em `avaliacao_bion/llm_ia/`.

A avaliação é **assíncrona**. A rota que inicia responde `202` na hora, e o front acompanha por uma rota leve de estado até a avaliação terminar. O conteúdo clínico só sai numa rota própria, que é auditada.

| Item | Valor |
|---|---|
| Blueprint | `bp_bion`, registrado em `/v1/api/bion` (`main.py`) |
| Quem acessa | Só o papel clínico `medico` (`@requer_papel_clinico("medico")`) |
| Cabeçalho de resposta | `Cache-Control: no-store` em todas as rotas, porque o dado clínico e o seu estado não podem ficar em cache de navegador ou proxy |
| Serviço | Uma instância criada na primeira chamada (`servico()`), porque precisa do app e do cliente de IA configurado |
| Erros de negócio | `BionException` vira `json_error(mensagem, status_code)` |

## Quem pode usar

Só o **médico do atendimento**, e só na **avaliação médica** ou na **reavaliação** em andamento. O rascunho de prescrição sai em nome de quem fez o atendimento. Enfermeiro e triagem seguem sem IA, pelos protocolos.

## Estados e erros que o front vê

| `status` | Significa |
|---|---|
| `processando` | Criada e enfileirada; o worker ainda não terminou |
| `concluido` | Resposta válida gravada e rascunho criado |
| `falhou` | Terminou sem proposta aproveitável; `erro_codigo` e `mensagem` explicam |

| `erro_codigo` | Causa |
|---|---|
| `ia_indisponivel` | O modelo não respondeu, o breaker estava aberto ou não há modelo configurado |
| `resposta_invalida` | Esgotou as 3 respostas válidas |
| `registro_proposta` | A IA respondeu, mas o rascunho não foi gravado |
| `fila_indisponivel` | Não foi possível enfileirar |
| `expirado` | Passou de 10 minutos em `processando` |
| `interno` | Erro inesperado |

`mensagem` só vem preenchida quando `status = falhou`. O front tem os próprios textos por `erro_codigo` e usa a `mensagem` do back apenas para um código que ainda não conhece.

---

# Rotas

| Método | Rota | Função | Auditoria |
|---|---|---|---|
| `POST` | `/atendimento/<uuid_atendimento>/avaliacao-bion` | Inicia a avaliação | Não |
| `GET` | `/avaliacao-bion/<uuid_output>/status` | Estado para o polling | Não (sem conteúdo clínico) |
| `GET` | `/atendimento/<uuid_atendimento>/avaliacao-bion/ultima` | Estado da avaliação mais recente do atendimento | Não (sem conteúdo clínico) |
| `GET` | `/avaliacao-bion/<uuid_output>` | Conteúdo da avaliação | **Sim**: `@acesso_auditado(recurso="avaliação do Bion", operacao="leitura")` |

Nenhuma rota recebe parâmetro de consulta. O `POST` não leva dado clínico: o back monta o input a partir do banco. O front manda `{}` como corpo, para manter o formato dos demais `POST`.

## POST `/atendimento/<uuid_atendimento>/avaliacao-bion`

Inicia a avaliação de forma assíncrona. Empresa e usuário vêm da sessão.

| Item | Detalhe |
|---|---|
| Parâmetro | `uuid_atendimento` na URL |
| Sucesso | `202`, mensagem "Avaliação iniciada.", `data: { uuid_output, status }` com `status = "processando"` |
| `403` | Não é médico, ou não é o profissional do atendimento |
| `404` | Atendimento inexistente ou de outra empresa |
| `409` | Tipo diferente de `avaliacao-medica` ou `reavaliacao`; atendimento fora de `em-andamento`; sem input de protocolo; já há avaliação em andamento; há rascunho de prescrição do próprio médico |
| Consentimento | Sem consentimento da consulta, o serviço de consulta recusa |
| Fila | Se não for possível enfileirar, a avaliação fica `falhou` com `fila_indisponivel` e o erro sobe |

Pré-requisito: o atendimento precisa ter um input de protocolo registrado, no atendimento atual ou em um atendimento clínico anterior finalizado da mesma consulta.

## GET `/avaliacao-bion/<uuid_output>/status`

Rota do polling. Devolve só o estado, sem conteúdo clínico e sem gerar linha de auditoria.

```json
{
  "uuid_output": "…",
  "status": "processando | concluido | falhou",
  "erro_codigo": null,
  "mensagem": null,
  "criado_em": "2026-11-07T12:00:00+00:00"
}
```

| Item | Detalhe |
|---|---|
| `404` | Avaliação inexistente ou de outra empresa |
| `403` | Não é o profissional do atendimento |
| Expiração | Um `processando` com mais de 10 minutos é mostrado como `falhou` com `erro_codigo = expirado`. É só leitura: nada é gravado |

## GET `/atendimento/<uuid_atendimento>/avaliacao-bion/ultima`

Estado da avaliação mais recente do atendimento, no mesmo formato do `status`. Serve para o front retomar depois de recarregar a página ou depois de um `409` de "já em andamento".

| Item | Detalhe |
|---|---|
| Sem avaliação | `data = null` |
| `403` | Não é o profissional do atendimento |
| `404` | Atendimento de outra empresa |

## GET `/avaliacao-bion/<uuid_output>`

Leitura **auditada** do conteúdo. Se a avaliação não estiver concluída, devolve só o estado, como o `status`. Se estiver, acrescenta:

| Campo | Conteúdo |
|---|---|
| `conduta_substituida` | `true` quando o rascunho desta avaliação foi trocado por uma avaliação mais nova |
| `precisa_mais_informacao` | A IA pediu mais dados |
| `perguntas` | Lista de `{ pergunta, motivo, bloco_relacionado }` |
| `explicacao` | Explicação para o profissional, no idioma pedido |
| `conduta` | Resultado da prescrição (`resultado_uuid`, `status`, `diagnostico`, `tipo_prescricao`, `medicamentos`, `exames`); `null` se não há rascunho |
| `diagnostico_proposto` | Preenchido quando a IA indicou diagnóstico sem medicamento nem exame |
| `qualidade` | `completude`, `confianca` (0 a 100) e `motivos` da confiança |
| `lacunas` | Dados que faltaram no envio |
| `blocos_considerados` | Blocos do input que a IA usou |

Em caso de erro, a rota devolve também `{"operacao": "NOOP"}` ao decorator. Sem isso, o decorator não olha o status HTTP e registraria um `403` ou `404` como leitura com sucesso.

---

# Como o front consome

| Peça do front | Comportamento |
|---|---|
| `avaliacaoBionApi.js` | Só `fetch`, com `credentials: "include"` e `cache: "no-store"`. Erros viram `ApiError` com a mensagem do back |
| `avaliacaoBionPolling.js` | Consulta `/status` a cada 3 s, passando a 5 s depois de 30 s; pausa com a aba oculta; tolera 2 falhas de rede ou `5xx` seguidas; teto de 11 min, que cobre o TTL de 10 min do back |
| `prescricaoIa.js` | Fluxo: `/ultima` ao abrir a página → `POST` → polling → uma única leitura completa → relê as prescrições, porque o rascunho já foi gravado |
| Bloqueio do botão | Desabilitado do clique até a resposta chegar, e por 30 s depois de `ia_indisponivel` |
| Mensagens | `exibirMensagem` para erro e sucesso; "carregando" e similares ficam só no painel |

Fluxo resumido: `POST` → consulta `/status` até `concluido` ou `falhou` → um único `GET` completo (gera uma linha de auditoria).

---

# Limites desta documentação

Descreve o código entregue em `avaliacao_bion.zip`. `controller.py` e o serviço só foram verificados por compilação, porque dependem de `src.models`, `src.core` e SQLAlchemy, que não rodam no sandbox. Nada foi executado contra o banco, o Gemini ou o front real.