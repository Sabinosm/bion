# Doença Crônica — Doenças crônicas do paciente

Documentação do módulo de doenças crônicas do paciente, com histórico de revisões. O fluxo completo está em `paciente_fluxo.md`.

---

# Contexto e conceitos

## Visão geral

A doença crônica é registrada com **CID-10**, data de início e status. Ela **não é editada no lugar**: status, CID e início são fatos clínicos com histórico, e mudam por **revisão**, que **fecha a linha vigente e cria uma nova**. Assim a linha do tempo de cada doença se preserva. Só `observacoes` (texto livre) muda no lugar.

## Quem lê e quem escreve

- **Leitura:** médico ou enfermeiro da empresa. A lista traz só as doenças **vigentes** (as encerradas por revisão são histórico, lido à parte); isso é o que aparece pré-preenchido em qualquer atendimento.
- **Escrita:** sempre dentro de um **Atendimento em andamento** do próprio profissional (checagem comum de escrita clínica). O registro guarda quem escreveu e em qual atendimento (criação, encerramento e remoção).

## Vigente, encerrada e removida

| Situação | Como se reconhece | Pode mudar |
|---|---|---|
| Vigente | Não removida e `encerrado_em` vazio | Sim |
| Encerrada por revisão | `encerrado_em` preenchido (aponta para a nova linha) | Não (409): atue no registro vigente |
| Removida | `deletado = true` | Não (409): restaure antes |

## Registrar

| Campo | Regra |
|---|---|
| `codigo_cid10` | Obrigatório; formato CID-10: letra + 2 dígitos + opcional `.` e 1 a 2 dígitos (`E11`, `E11.9`); vai para maiúsculas |
| `descricao_cid10` | Obrigatório; até 255 caracteres; não pode ser só espaços |
| `desde` | Obrigatório; não pode ser futura |
| `status` | Obrigatório: `ativa` ou `em-remissao` |
| `observacoes` | Opcional; até 2000 caracteres |

| Regra | Erro |
|---|---|
| Corpo inválido (erros por campo) | 422 |
| Já existe doença **vigente** com o mesmo CID | 409 |

## Atualizar (observações)

Só `observacoes`. Enviar `codigo_cid10`, `descricao_cid10`, `desde` ou `status` devolve 422 com a orientação de usar `/revisar`. `observacoes: null` limpa o texto; omitir o campo é erro (corpo vazio não é atualização). 404 se a doença não existe ou é de outro paciente; 409 se está removida ou encerrada.

## Revisar

O que vier preenchido substitui o valor vigente na **linha nova**; o que não vier é copiado da vigente. Regras do corpo:

- ao menos um de `codigo_cid10`, `descricao_cid10`, `desde` e `status`;
- `codigo_cid10` e `descricao_cid10` andam **juntos**;
- `observacoes` é opcional (omitida copia; `null` limpa).

A linha vigente é encerrada (quem, quando e em qual atendimento) e aponta para a nova. Devolve a **nova linha**.

| Regra | Erro |
|---|---|
| Nenhuma mudança real em relação à vigente | 422 |
| Doença removida ou já encerrada | 409 |
| O novo CID já existe vigente em outra linha | 409 |

## Remover e restaurar

**Remover** é *soft delete* com motivo (`erro-digitacao`, `registro-duplicado`, `diagnostico-incorreto`, `solicitacao-paciente` ou `outro`; com `outro`, `observacoes_delete` é obrigatória). Só a linha **vigente** é removida; linha encerrada é histórico e corrige-se revisando a vigente. Remover de novo cai em 404. É **ação sensível** (step-up, justificativa e log atômico).

**Restaurar** reverte o soft delete. 409 se não está removida, ou se já existe outra vigente com o mesmo CID.

## Transação

Os métodos de escrita aceitam `commit`: com `False` só fazem flush e o commit é de quem compõe a operação (ação sensível, rota agregada do binário). Revisar insere a linha nova (flush, para obter o id) e fecha a antiga **na mesma unidade**.

## Estatísticas

`top_cid_ativas` devolve o ranking de CID com `status = ativa` entre os pacientes da empresa. Conta só linhas **vigentes e não removidas**: uma linha encerrada por revisão continua com `status = ativa` na linha antiga e inflaria o ranking.

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `controllers/doenca_cronica_controller.py` | Rotas (`bp` de leitura e `bp_escrita`) |
| `services/doenca_cronica_service.py` | Regras |
| `repositories/doenca_cronica_repository.py` | Acesso a dados e estatística |
| `schemas/schema_doenca_cronica.py` | Schemas de entrada |
