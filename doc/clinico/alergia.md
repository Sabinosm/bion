# Alergia — Alergias e reações do paciente

Documentação do módulo de alergias: a alergia (a substância) e as suas reações (o histórico de ocorrências). O ciclo do atendimento está em `atendimento.md` (pasta de docs do atendimento) e o fluxo completo em `paciente_fluxo.md`.

---

# Contexto e conceitos

## Visão geral

A **Alergia** registra a substância; cada **Reação** é uma ocorrência (manifestação, gravidade, data). A alergia nasce **já com a primeira reação**. Não pode haver duas alergias **ativas** à mesma substância: uma nova ocorrência vai como reação na alergia existente.

## Quem lê e quem escreve

- **Leitura:** médico ou enfermeiro da empresa (o paciente é buscado pela empresa da sessão, com 404 uniforme).
- **Escrita:** sempre **dentro de um Atendimento em andamento** do próprio profissional, pela checagem comum de escrita clínica (dono do atendimento, mesmo paciente, enfermeiro só em triagem, paciente sem óbito). O registro guarda quem escreveu e em qual atendimento (criação e remoção).

## Alergia

| Campo (criação) | Regra |
|---|---|
| `substancia` | Obrigatório; até 255 caracteres; não pode ser só espaços |
| `codigo_substancia` | Opcional; até 100 caracteres |
| `flag_confirmado` | Padrão `false` |
| `tipo_reacao` | Obrigatório: `cutanea`, `respiratoria`, `anafilaxia`, `gastrointestinal`, `cardiovascular` ou `sistemica` |
| `gravidade` | Obrigatório: `leve`, `moderada` ou `grave` |
| `descricao_reacao` | Opcional; até 2000 caracteres |

Consistência clínica: **anafilaxia** só aceita gravidade `moderada` ou `grave` (422 caso contrário).

| Regra | Erro |
|---|---|
| Corpo inválido (erros por campo) | 422 |
| Já existe alergia ativa à mesma substância (sem diferenciar maiúscula; a insensibilidade a acento depende da collation) | 409 |

## Atualizar

Só `codigo_substancia` e `flag_confirmado` mudam. A **substância não é editável**: a alergia tem reações registradas contra ela, e mudar o nome deixaria as antigas presas a outro rótulo. Se a substância foi cadastrada errada, remove-se e cria-se de novo. A mudança fica no log de auditoria.

| Regra | Erro |
|---|---|
| Alergia existe e é do paciente | 404 |
| Alergia não está removida (restaure antes de editar) | 409 |

## Reação

| Campo | Regra |
|---|---|
| `manifestacao` | As mesmas manifestações da alergia |
| `gravidade` | `leve`, `moderada` ou `grave` (mesma regra da anafilaxia) |
| `descricao` | Opcional; até 2000 caracteres |
| `data_ocorrencia` | Opcional; não pode ser futura |

Adicionar devolve a alergia atualizada (404 se a alergia não existe, está removida ou é de outro paciente). Reação é histórico imutável: uma reação errada se corrige **removendo e recriando**.

## Remover e restaurar

**Remover** é *soft delete*, com motivo, autor e atendimento da remoção; nada é apagado (as reações ficam junto). Motivos: `erro-digitacao`, `registro-duplicado`, `diagnostico-incorreto`, `solicitacao-paciente` ou `outro`; com `outro`, `observacoes_delete` é obrigatória (até 2000 caracteres). O mesmo contrato vale para remover uma **reação** (só aquela reação; a alergia e as demais ficam). Remover de novo cai em 404.

Remover alergia é **ação sensível** (step-up, justificativa e log de alteração na mesma transação).

**Restaurar** reverte o soft delete. 409 se a alergia não está removida, ou se já existe outra ativa à mesma substância.

---

# Transação

Os métodos de escrita aceitam `commit`: com `False` só fazem flush, e o commit é de quem compõe a operação (ação sensível, rota agregada do binário). Com `True`, uma falha desfaz tudo.

# Estatísticas

| Método do service | O que devolve |
|---|---|
| `top_substancias` | Substâncias mais reportadas na empresa |
| `gravidade_por_substancia` | Distribuição de gravidade das reações de uma substância |
| `gravidade_geral` | Distribuição de gravidade das reações não removidas de todas as alergias não removidas da empresa |

A empresa vem de `Paciente.id_empresa`. Alergia removida **e reação removida** não entram nas distribuições de gravidade (o ranking de substâncias também ignora alergia removida).

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `controllers/alergia_controller.py` | Rotas (`bp` de leitura e `bp_escrita`) |
| `services/alergia_service.py` | Regras da alergia |
| `services/reacao_alergia_service.py` | Regras das reações |
| `repositories/alergia_repository.py` | Acesso a dados da alergia e estatísticas |
| `repositories/reacao_alergia_repository.py` | Acesso a dados das reações |
| `schemas/schema_alergia.py` | Schemas de entrada |
