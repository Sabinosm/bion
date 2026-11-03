# Resultado da Prescrição — Diagnóstico e ciclo do rascunho

Documentação do módulo do `ResultadoPrescricao`: o diagnóstico (CID-10), o desfecho clínico e o ciclo de vida do rascunho (registrar, corrigir, confirmar e descartar). Os medicamentos prescritos estão em `prescricao.md`, os exames em `prescricao_exame.md` e o fluxo completo em `prescricao_fluxo.md`.

---

# Contexto e conceitos

## Visão geral

Cada **Atendimento** pode ter vários `ResultadoPrescricao`, mas só um em **rascunho** por vez. O resultado guarda o diagnóstico e a categoria da prescrição, e os itens (medicamentos e exames) ficam pendurados nele. O médico monta o rascunho, revisa e **confirma**; só então a prescrição passa a valer e entra nas estatísticas.

Sem step-up: a prescrição acontece durante o atendimento e o médico não deve ser interrompido. A rastreabilidade vem do log de acesso (quem, quando, o quê) e do próprio registro (origem, descarte).

## Status

| Status | Significa |
|---|---|
| `rascunho` | Em edição. Aceita alterações do diagnóstico e dos itens |
| `confirmado` | O médico responsável passou a responder pela prescrição. Não altera mais nem se descarta |
| `descartado` | Descarte **lógico** (nada é apagado), com data, autor e motivo opcional |

## Origem do resultado

A origem do **resultado** (quem responde pelo conteúdo agora) não se confunde com a origem de cada item.

| Origem | Significa |
|---|---|
| `bion_ia` | Criado a partir da proposta da IA |
| `medico` | Criado pelo médico, ou alterado por ele depois |

**Qualquer alteração do médico** (diagnóstico, adição, alteração ou remoção de item) passa a origem do resultado para `medico`, na mesma transação, e a IA deixa de poder trocá-lo. A sugestão original da IA continua registrada no envio à IA.

## Invariantes

- Só o **médico dono do atendimento** escreve, e só com o atendimento **em andamento**. Descartar um rascunho antigo é a única escrita permitida fora de `em-andamento`.
- No máximo **um rascunho por atendimento** no fluxo do médico. A criação **trava o atendimento** (`SELECT ... FOR UPDATE`) antes de checar os rascunhos, então duas requisições simultâneas não criam dois. A IA só coexiste com rascunhos da própria IA (trocados logo depois) e **nunca** com rascunho do médico.
- Toda alteração de um resultado existente (itens, diagnóstico, confirmação) **trava a linha do resultado** até o commit, e o status é conferido depois da trava. Duas alterações simultâneas do mesmo resultado se serializam (por exemplo, o mesmo medicamento adicionado duas vezes).
- A empresa é a da **Consulta** do atendimento. "Não existe" e "é de outra empresa" dão o mesmo 404.

---

# Diagnóstico

Corpo de criação (`ResultadoPrescricaoIn`):

| Campo | Regra |
|---|---|
| `codigo_cid10_principal` | Obrigatório. CID-10: letra + 2 dígitos e subcategoria opcional (`A90`, `J45.9`, `S72.01`). Vai para maiúsculas |
| `descricao_cid10_principal` | Obrigatório. Até 255 caracteres |
| `certeza_diagnostica` | Obrigatório. `suspeito`, `provavel`, `confirmado` ou `descartado` |
| `tipo_prescricao` | Opcional. `farmacologica`, `nao-farmacologica`, `encaminhamento`, `internacao` ou `alta` |

`status`, `formulado_por`, `id_output` e `consistente_com_classificacao` **não** entram no corpo: são definidos pelo servidor. Qualquer campo fora do contrato é recusado (422), em vez de ser ignorado. Texto em branco vale como ausente.

## Correção (PATCH)

Só os campos enviados mudam. Regras: é preciso enviar ao menos um campo; `codigo_cid10_principal`, `descricao_cid10_principal` e `certeza_diagnostica` **não aceitam vazio**; `tipo_prescricao` pode ser limpo com `null`. Se nenhum valor realmente mudou, nada é gravado e a origem **não** muda.

---

# Registrar o rascunho

Validações, nesta ordem:

| Regra | Erro |
|---|---|
| Atendimento existe na empresa | 404 |
| O usuário é o profissional do atendimento | 403 |
| Atendimento em andamento | 409 |
| Fluxo do médico: não há outro rascunho no atendimento | 409 |
| Fluxo da IA: não há rascunho do **médico** no atendimento | 409 |

O resultado nasce em `rascunho`, com `formulado_por` = o médico da sessão. A origem é `bion_ia` quando há envio de origem (só o fluxo da IA informa) e `medico` caso contrário; o envio de origem **nunca** vem do corpo.

## Rascunho editável

Antes de qualquer alteração (diagnóstico, itens) e da confirmação, o service exige um resultado:

| Regra | Erro |
|---|---|
| Existe na empresa | 404 |
| O usuário é o médico que o formulou | 403 |
| Não está `confirmado` | 409 |
| Não está `descartado` | 409 |
| O atendimento está em andamento | 409 |

---

# Confirmar

O médico responsável passa a responder pela prescrição (`rascunho` → `confirmado`, com `confirmado_em`).

- Se o `tipo_prescricao` é `farmacologica`, é preciso ao menos **um medicamento** (409).
- As **interações** são verificadas entre os medicamentos da prescrição e também **com os medicamentos que o paciente já usa** (registros ativos). Havendo alertas, a confirmação exige o reconhecimento explícito, com `reconhecer_alertas = true` (409 caso contrário, informando a quantidade de alertas).
- A resposta traz o resultado e a verificação (`alertas` e `cobertura`).

# Descartar

Descarte lógico do rascunho, com `descartado_em`, `descartado_por` e `motivo_descarte` (opcional, até 255 caracteres). Vale **mesmo com o atendimento já finalizado ou cancelado**, para não deixar rascunho preso. Só o médico que o formulou (403); resultado `confirmado` não se descarta (409) e `descartado` não se descarta de novo (409).

---

# Leituras

| Consulta | Quem | Observação |
|---|---|---|
| Resultados do atendimento | Médico dono do atendimento | Do mais antigo ao mais novo, em qualquer status do atendimento (histórico). É por aqui que a tela reencontra o rascunho depois de recarregar |
| Detalhe de um resultado (com itens) | Médico ou enfermeiro da empresa | Pelo UUID, só da própria empresa |
| Alertas de interação | Médico da empresa | Interações do conjunto atual de medicamentos, entre si e com os que o paciente já usa |

Os alertas trazem também a **cobertura** da base: lista vazia **não** significa ausência de interação clínica (ver `prescricao.md`).

---

# Estatísticas

O repository agrega só resultados **confirmados** e filtra pela empresa da Consulta.

| Método do service | O que devolve |
|---|---|
| `top_cid_por_regiao` | Ranking de CID-10 por região geográfica do **paciente** (não da empresa) |
| `total_casos_por_regiao` | Total de diagnósticos por região, com a população estimada (base da incidência por 100 mil; a divisão fica na camada de estatística) |
| `evolucao_cid` | Série diária de casos de um CID nos últimos N dias |
| `evolucao_cid_periodo` | Mesma série com janela `[inicio, fim)`, para comparar o período anterior |

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `resultado_prescricao/resultado_prescricao_controller.py` | Rotas (blueprint `resultado_prescricao`) |
| `resultado_prescricao/resultado_prescricao_service.py` | Regras do ciclo do rascunho e leituras |
| `resultado_prescricao/resultado_prescricao_repository.py` | Acesso a dados e agregações |
| `schema_prescricoes.py` | Schemas de entrada (compartilhado com medicamentos, exames e IA) |
| `prescricao_controller_helpers.py` | Leitura do corpo e respostas de erro dos controllers |
