# Medicamento em Uso — Medicamentos que o paciente já usa

Documentação do módulo de medicamentos em uso: registrar, substituir, encerrar, remover e restaurar, a verificação de interações e a estatística de uso contínuo. O fluxo completo está em `paciente_fluxo.md`.

---

# Contexto e conceitos

## Visão geral

O medicamento em uso é o tratamento **que o paciente já faz** (diferente do medicamento *prescrito* no atendimento). Não há atualização no lugar: mudar dose ou frequência é **substituir** (fecha o antigo e cria o novo, numa transação só).

## Quem lê e quem escreve

- **Leitura:** médico ou enfermeiro da empresa.
- **Escrita:** dentro de um **Atendimento em andamento** do próprio profissional (checagem comum de escrita clínica).

## Situação do registro

| `status_uso` | Significa |
|---|---|
| `ativo` | Em uso (só o ativo muda) |
| `concluido` | Tratamento terminou (ou foi substituído por outro) |
| `interrompido` | Tratamento interrompido |

Registro **removido** ou **já encerrado** vale 409 ao tentar alterar.

## Registrar

| Campo | Regra |
|---|---|
| `uuid_catalogo` | Opcional; UUID de um medicamento do catálogo (nunca o id interno) |
| `descricao` | Obrigatória **sem** catálogo; com catálogo, se vier vazia o service usa o princípio ativo do catálogo. Até 2000 caracteres |
| `dose`, `frequencia` | Opcionais; até 100 caracteres |
| `desde` | Opcional; não pode ser futura |

O registro nasce `ativo`. Devolve também os **alertas de interação** já considerando o novo item.

| Regra | Erro |
|---|---|
| Corpo inválido (erros por campo) | 422 |
| `uuid_catalogo` inexistente no catálogo | 422 |
| Sem descrição e sem catálogo | 422 |
| O mesmo medicamento do catálogo já está **ativo** para o paciente | 409 |

## Substituir

Para mudança de dose, frequência ou descrição: cria o registro novo e fecha o antigo (`concluido`, com `ate` = data da mudança), apontando para o novo. Devolve o **registro novo**.

- É preciso enviar ao menos um de `descricao`, `dose` e `frequencia`; o que não vier é copiado do antigo.
- `data_mudanca` omitida = hoje **no fuso da empresa**; vira o `ate` do antigo e o `desde` do novo. Não pode ser futura nem anterior ao início do uso.
- Nenhuma alteração real em relação ao atual dá 422.
- 409 se o registro está removido ou já encerrado.

## Encerrar

Fecha o tratamento como `interrompido` ou `concluido`, com `ate` (omitido = hoje no fuso da empresa; não futuro e não anterior ao início do uso, 422). 409 se removido ou já encerrado.

## Remover e restaurar

**Remover** é *soft delete* com motivo (`erro-digitacao`, `registro-duplicado`, `diagnostico-incorreto`, `solicitacao-paciente` ou `outro`; com `outro`, `observacoes_delete` é obrigatória). Não mexe no estado clínico (`status_uso` e `ate`). Remover de novo cai em 404. É **ação sensível** (step-up, justificativa e log atômico).

**Restaurar** reverte o soft delete. É também ação sensível. 409 se não está removido, ou se já existe outro registro **ativo** do mesmo medicamento do catálogo.

## Transação

Os métodos de escrita aceitam `commit`; com `False` só fazem flush, e o commit é do chamador (a ação sensível comita a alteração e o log numa transação única, por isso o controller não comita). Se qualquer flush ou commit falhar, a sessão inteira sofre rollback.

---

# Verificação de interações

Cruza os medicamentos **ativos com vínculo no catálogo** com o catálogo de interações. É **informativa e não bloqueia nada**.

| Campo | Conteúdo |
|---|---|
| `interacoes` | Para cada par: `uuid`, `medicamento_a`, `medicamento_b` (princípios ativos), `gravidade`, `mecanismo_efeito`, `recomendacao`, `acao` |
| `nao_verificados` | Ativos **sem** vínculo com o catálogo (`uuid`, `descricao`), que não entram na checagem |
| `cobertura` | `total_interacoes_na_base` e `aviso` |

**Lista vazia não significa ausência de interação clínica**: a base cobre só o que está cadastrado. O aviso diz isso, ou "Base de interações ainda vazia: nenhuma checagem foi possível.", e acrescenta que há medicamentos sem vínculo quando for o caso.

# Estatísticas

`percentual_pacientes_em_uso_continuo` devolve `total_pacientes`, `em_uso_continuo` (pacientes distintos com ao menos um medicamento ativo e não removido) e `percentual`, sobre o total de pacientes da empresa.

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `controllers/medicamentos_em_uso_controller.py` | Rotas (`bp` de leitura e `bp_escrita`) |
| `services/medicamento_em_uso_service.py` | Regras e verificação de interações |
| `repositories/medicamento_em_uso_repository.py` | Acesso a dados e estatística |
| `schemas/schema_medicamento_em_uso.py` | Schemas de entrada |
