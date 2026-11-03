# Prescrição de Exames

Documentação do módulo dos exames prescritos: adicionar, alterar e remover exames do rascunho de prescrição. O diagnóstico e o ciclo do rascunho estão em `resultado_prescricao.md`, os medicamentos em `prescricao.md` e o fluxo completo em `prescricao_fluxo.md`.

---

# Contexto e conceitos

## Visão geral

O exame prescrito (`PrescricaoExame`) pertence a um `ResultadoPrescricao` em **rascunho**, no mesmo molde dos medicamentos: o médico monta a lista e a IA pode propor exames pelo mesmo caminho de criação. O exame é referenciado pelo **UUID público** do catálogo (`uuid_exame`), nunca pelo id numérico interno.

O catálogo de exames ainda está por planejar: a busca assume o mesmo padrão dos outros catálogos (coluna `uuid`) e passa a viver no repositório do catálogo quando ele existir.

## Quem pode escrever

Só o **médico dono** do atendimento, com o resultado em rascunho e o atendimento em andamento (regras do rascunho editável em `resultado_prescricao.md`). Origem e envio de origem do item são decididos por quem chama (médico ou IA), **nunca** pelo corpo da requisição.

| `origem_sugestao` | Significa |
|---|---|
| `bion_ia` | Sugerido pela IA e ainda não mexido pelo médico |
| `medico` | Adicionado pelo médico, ou sugestão da IA que ele alterou |

Adicionar, alterar ou remover um exame passa a origem do **resultado** para `medico`, na mesma transação.

---

# Exame prescrito

Corpo de adição (`ExamePrescritoIn`):

| Campo | Regra |
|---|---|
| `uuid_exame` | Obrigatório. UUID de um exame do catálogo |
| `urgencia` | Opcional. `rotina` (padrão), `urgente` ou `emergencia` |
| `justificativa` | Opcional. Até 2000 caracteres |

Campos fora do contrato são recusados com 422, e texto em branco vale como ausente.

| Regra | Erro |
|---|---|
| Exame existe no catálogo | 404 |
| O exame **não** consta ainda no resultado | 409 |

Cada alteração trava a linha do resultado até o commit, então duas requisições simultâneas do mesmo exame se serializam.

## Alterar (PATCH)

Altera urgência ou justificativa; só o que foi enviado muda. É preciso enviar ao menos um campo. A `urgencia` **não aceita** `null` ou vazio; a `justificativa` aceita (limpa o campo). Se nenhum valor realmente mudou, nada é gravado e a origem não muda; se mudou, o item e o resultado passam a `medico`.

## Remover

Remove o exame do rascunho, inclusive sugestões da IA que o médico descartou. O resultado passa a ser do médico. Item inexistente **neste resultado** dá 404.

---

# Estatísticas

| Método do service | O que devolve |
|---|---|
| `urgencia_por_origem` | Contagem de exames prescritos cruzando **urgência x origem** (IA x profissional), nos últimos N dias |

Conta só exames de resultados **confirmados**, das Consultas da empresa. O recorte de tempo usa a data de criação do exame.

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `prescricao_exame/prescricao_exame_controller.py` | Rotas (blueprint `prescricao_exame`) |
| `prescricao_exame/prescricao_exame_service.py` | Regras de adição, alteração e remoção; criação única para médico e IA |
| `prescricao_exame/prescricao_exame_repository.py` | Acesso a dados, busca no catálogo e agregação |
| `schema_prescricoes.py` | Schemas de entrada (compartilhado) |
| `prescricao_controller_helpers.py` | Leitura do corpo e respostas de erro dos controllers |
