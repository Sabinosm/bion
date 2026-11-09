# Prescrição — Medicamentos prescritos, interações e proposta da IA

Documentação do módulo dos medicamentos prescritos: adicionar, alterar e remover medicamentos do rascunho, a verificação de interações medicamentosas e o registro da proposta da IA. O diagnóstico e o ciclo do rascunho estão em `resultado_prescricao.md`, os exames em `prescricao_exame.md` e o fluxo completo em `prescricao_fluxo.md`.

---

# Contexto e conceitos

## Visão geral

O medicamento prescrito (`Prescricao`) pertence a um `ResultadoPrescricao` em **rascunho**. O médico monta a lista; a IA pode propor itens pelo mesmo caminho de criação. O medicamento é sempre referenciado pelo **UUID público** do catálogo (`uuid_catalogo`), nunca pelo id numérico interno.

## Quem pode escrever

Só o **médico dono** do atendimento, com o resultado em rascunho e o atendimento em andamento (as regras do rascunho editável estão em `resultado_prescricao.md`). Origem e envio de origem do item são decididos por quem chama (médico ou IA), **nunca** pelo corpo da requisição. Cada alteração trava a linha do resultado até o commit, então duas requisições simultâneas (por exemplo, o mesmo medicamento adicionado duas vezes) se serializam.

## Origem do item

| `origem_sugestao` | Significa |
|---|---|
| `bion_ia` | Sugerido pela IA e ainda não mexido pelo médico |
| `medico` | Adicionado pelo médico, ou sugestão da IA que ele alterou |

Alterar um item (ou adicionar, ou remover) passa a origem do **resultado** para `medico`, na mesma transação.

---

# Medicamento prescrito

Corpo de adição (`MedicamentoPrescritoIn`):

| Campo | Regra |
|---|---|
| `uuid_catalogo` | Obrigatório. UUID de um medicamento do catálogo |
| `dose` | Opcional. Até 100 caracteres |
| `frequencia` | Opcional. Até 100 caracteres |
| `duracao` | Opcional. Até 100 caracteres |
| `orientacoes` | Opcional. Até 2000 caracteres |

Campos fora do contrato (`origem_sugestao`, `id_output_origem`, `id_resultado`, `status`...) são recusados com 422. Texto em branco vale como ausente.

| Regra | Erro |
|---|---|
| Medicamento existe no catálogo | 404 |
| O medicamento **não** consta ainda no resultado | 409 |

## Alterar (PATCH)

Altera dose, frequência, duração ou orientações; só o que foi enviado muda, e `null` ou vazio **limpa** o campo. É preciso enviar ao menos um campo. Trocar o medicamento é remover e adicionar outro. Se **nenhum valor realmente mudou**, nada é gravado e a origem não muda; se mudou, o item e o resultado passam a `medico`.

## Remover

Remove o item do rascunho, inclusive sugestões da IA que o médico descartou. O resultado passa a ser do médico. Item inexistente **neste resultado** dá 404, sem distinguir "não existe" de "é de outro resultado".

## Resposta da adição

A adição devolve o item e os alertas de interação do conjunto atual do rascunho: `{ "prescricao": {...}, "alertas": [...], "cobertura": {...} }`.

---

# Verificação de interações

A checagem é **determinística** contra o catálogo de medicamentos e **não bloqueia nada**: devolve alertas e a cobertura da base, e quem decide é o médico (a confirmação exige o reconhecimento dos alertas; ver `resultado_prescricao.md`).

| Parte | Conteúdo |
|---|---|
| `alertas` | Uma entrada por interação cadastrada: os dados da interação, `medicamento_a`, `medicamento_b` (princípios ativos) e `contexto` |
| `cobertura.total_interacoes_na_base` | Quantas interações a base conhece |
| `cobertura.escopo` | `["itens_prescritos", "medicamentos_em_uso"]`: a checagem cobre os itens da prescrição e os medicamentos que o paciente já usa |
| `cobertura.aviso` | Texto de cautela |

`contexto` vale `entre_itens_prescritos` (os dois medicamentos estão na prescrição) ou `com_medicamento_em_uso` (um deles é de uso do paciente). Os medicamentos em uso são os registros **ativos** do paciente do atendimento; um medicamento que está na prescrição e também em uso conta como item prescrito.

**Lista vazia nunca deve ser apresentada como "sem interação"**: o catálogo só conhece as interações cadastradas, e a fonte atual não traz gravidade. O aviso é "Base de interações ainda vazia." quando não há nenhuma interação na base, ou "Lista vazia não significa ausência de interação clínica: a base cobre apenas as interações cadastradas." nos demais casos.

Contraindicações e alergias ainda não entram na verificação: a contraindicação é um vocabulário fechado, sem ligação com o quadro do paciente, e o cruzamento depende de um mapeamento a definir.

---

# Proposta da IA

A IA responde no formato `PropostaPrescricaoIA`, validado pelas **mesmas classes** que as rotas do médico.

| Campo | Regra |
|---|---|
| `resultado` | Diagnóstico (mesmos campos do corpo de criação). Obrigatório quando há itens |
| `medicamentos` | Até 20 itens, sem repetir `uuid_catalogo` |
| `exames` | Até 20 itens, sem repetir `uuid_exame` |

Sem medicamentos e sem exames = **sem recomendação**: nada é criado e o registro fica só no envio à IA (retorno nulo). Com itens, o serviço cria, **em uma única transação**, o resultado em rascunho (origem `bion_ia`) e todos os itens (origem `bion_ia`, com o envio de origem). Qualquer item inválido (UUID inexistente, repetido) desfaz tudo.

Também nada é salvo (409) se o atendimento já não está em andamento ou se há rascunho do médico: o worker não escreve em atendimento finalizado ou cancelado, nem por cima do que o médico está editando. O usuário precisa ser o profissional do atendimento (403).

---

# Estatísticas

O repository agrega só prescrições de resultados **confirmados** e filtra pela empresa da Consulta.

| Método do service | O que devolve |
|---|---|
| `top_por_classe` | Ranking das classes farmacêuticas mais prescritas nos últimos N dias |
| `top_principios_ativos_por_classe` | Princípios ativos mais prescritos dentro de uma classe (detalhe do ranking) |

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `prescricao_controller.py` | Rotas (blueprint `prescricao`) |
| `prescricao_service.py` | Regras de adição, alteração e remoção; criação única para médico e IA |
| `prescricao_repository.py` | Acesso a dados e agregações |
| `prescricao_validacao_service.py` | Verificação de interações |
| `prescricao_ia_service.py` | Registro da proposta da IA |
| `schema_prescricoes.py` | Schemas de entrada (compartilhado) |
| `prescricao_controller_helpers.py` | Leitura do corpo e respostas de erro dos controllers |
