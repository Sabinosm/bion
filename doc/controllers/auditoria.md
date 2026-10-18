# Controllers de Auditoria

Rotas HTTP do domínio de auditoria (`controller.py`, blueprint `auditoria`). O prefixo das URLs depende de como o blueprint é registrado na aplicação; os caminhos abaixo são relativos a ele.

Para o funcionamento interno (logs, step-up, período, cursor), ver `auditoria_fluxo.md`.

---

# Convenções gerais

| Tema | Regra |
|---|---|
| Acesso | Todas as rotas exigem administrador (`@requer_admin`) |
| Escopo | Sempre a empresa da sessão; não é possível consultar outra |
| Método | Todas são `GET` |
| Sucesso | `json_success(data=...)` |
| Datas | ISO 8601 (ex.: `2026-10-18T09:30:00`) |
| Identificação de usuário | Sempre por `uuid`, nunca por id interno |

## Parâmetros comuns

| Parâmetro | Tipo | Padrão | Observação |
|---|---|---|---|
| `page` | inteiro | `1` | Mínimo 1; valores menores viram 1 |
| `limit` | inteiro | `10` | Máximo 50; vazio ou não positivo volta a 10 |
| `data_inicio` / `data_fim` | ISO 8601 | últimos 7 dias | Janela de 7 dias; se só uma vier, a outra é completada (ver abaixo) |

## Janela de período

Vale para `/acessos`, `/alteracoes` (listagem) e `/profissionais/<uuid>/detalhe`.

| Enviado | Efeito |
|---|---|
| Só `data_inicio` | `data_fim` = `data_inicio` + 7 dias |
| Só `data_fim` | `data_inicio` = `data_fim` - 7 dias |
| As duas | Valida `data_fim >= data_inicio` e intervalo de até 7 dias |
| Nenhuma | Últimos 7 dias (`data_fim` = agora em UTC) |

## Formato de paginação por offset

```json
{
  "itens": [],
  "paginacao": { "total": 0, "page": 1, "limit": 10 }
}
```

## Formato de bloco paginado por cursor

```json
{
  "itens": [],
  "tem_mais": false,
  "proximo_cursor": { "cursor_data": "...", "cursor_uuid": "..." }
}
```

`proximo_cursor` é `null` quando o bloco vem vazio.

---

# Rotas

## `GET /profissionais/resumo`

Lista profissionais paginados, em ordem alfabética, cada um com o último log de acesso e de alteração. Só aparecem profissionais com ao menos um log.

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `nome` | texto | não | Busca por parte do nome |
| `funcao_clinica` | texto | não | `medico` ou `enfermeiro` |
| `is_admin` | texto | não | `true` ou `false` |
| `acao` | texto | não | Ação (texto livre) ou categoria de operação |
| `page`, `limit` | inteiro | não | Paginação por offset |

`funcao_clinica` e `is_admin` combinam entre si.

**Resposta:** formato de paginação por offset. Cada item:

| Campo | Descrição |
|---|---|
| `uuid_usuario` | UUID do profissional |
| `nome` | Nome completo |
| `ultimo_acesso` | Resumo do último log de acesso (ausente se não houver) |
| `ultima_alteracao` | Resumo do último log de alteração (ausente se não houver) |

---

## `GET /profissionais/<uuid_usuario>/detalhe`

Histórico cronológico (do mais recente ao mais antigo) de acessos e alterações de um profissional. Os dois blocos paginam por cursor, de forma independente.

| Parâmetro | Local | Obrigatório | Descrição |
|---|---|---|---|
| `uuid_usuario` | caminho | sim | UUID do profissional |
| `acao` | query | não | Filtro aplicado aos dois blocos (ver observação) |
| `operacao_acesso` | query | não | Filtro extra só do bloco de acessos; tem precedência sobre `acao` nele |
| `data_inicio`, `data_fim` | query | não | Período, com a janela de 7 dias |
| `limit` | query | não | Itens por bloco |
| `cursor_acessos_data` | query | não | `cursor_data` recebido no bloco de acessos |
| `cursor_acessos_uuid` | query | não | `cursor_uuid` recebido no bloco de acessos |
| `cursor_alteracoes_data` | query | não | `cursor_data` recebido no bloco de alterações |
| `cursor_alteracoes_uuid` | query | não | `cursor_uuid` recebido no bloco de alterações |

Os nomes dos campos de cursor na resposta (`cursor_data`, `cursor_uuid`) diferem dos nomes enviados na requisição, que levam o prefixo do bloco (`cursor_acessos_...`, `cursor_alteracoes_...`). Sem a data, o cursor é ignorado e a consulta começa do mais recente.

**Resposta:**

```json
{
  "acessos":    { "itens": [], "tem_mais": false, "proximo_cursor": null },
  "alteracoes": { "itens": [], "tem_mais": false, "proximo_cursor": null }
}
```

O cursor de acessos usa `data_hora` do último item; o de alterações usa `alterado_em`.

Se o `uuid_usuario` não existir na empresa, a rota devolve os dois blocos vazios.

**Filtro `acao`:** mesma regra do resumo. No bloco de alterações compara com o texto livre da ação (ex.: `editar_paciente`) ou com a categoria traduzida (ex.: `escrita` = `INSERT`/`UPDATE`); no bloco de acessos compara com a categoria. Como o log de acesso não tem ação em texto livre, uma ação de texto livre só retorna itens em `alteracoes`.

---

## `GET /acessos`

Lista registros de acesso filtrados, com paginação por offset, do mais recente ao mais antigo.

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `uuid_usuario` | texto | não | Filtra pelo usuário que acessou |
| `nome` | texto | não | Busca por parte do nome do usuário |
| `operacao` | texto | não | `leitura`, `escrita`, `exclusao-logica` ou `exportacao` |
| `data_inicio`, `data_fim` | ISO 8601 | não | Período, com a janela de 7 dias |
| `page`, `limit` | inteiro | não | Paginação por offset |

**Resposta:** formato de paginação por offset, com os logs serializados por `to_dict()`.


---

## `GET /alteracoes`

Lista alterações de dados. Tem dois modos, escolhidos pelos parâmetros.

**Modo listagem** (padrão): filtros combináveis e paginação por offset, do mais recente ao mais antigo.

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `uuid_usuario` | texto | não | Filtra pelo usuário que alterou |
| `nome` | texto | não | Busca por parte do nome do usuário |
| `acao` | texto | não | Igual à ação gravada (texto livre) |
| `operacao` | texto | não | Categoria (`escrita`, `exclusao-logica`) ou `INSERT`/`UPDATE`/`DELETE`; categorias sem equivalente (ex.: `leitura`) retornam lista vazia |
| `data_inicio`, `data_fim` | ISO 8601 | não | Período, com a janela de 7 dias |
| `page`, `limit` | inteiro | não | Paginação por offset |

**Resposta:** formato de paginação por offset.

**Modo drill-down**: ativado quando `tabela` **e** `uuid_registro` são enviados juntos. Devolve o histórico completo de alterações daquele registro, sem paginação, ignorando todos os outros filtros e o período.

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `tabela` | texto | sim (no modo) | Tabela de origem do registro |
| `uuid_registro` | texto | sim (no modo) | UUID do registro alterado |

**Resposta:** `{ "itens": [...] }`, sem o bloco `paginacao`.


---

# Resumo das rotas

| Método | Rota | Paginação | Período | Retorno |
|---|---|---|---|---|
| GET | `/profissionais/resumo` | offset | não | Profissionais com último acesso/alteração |
| GET | `/profissionais/<uuid_usuario>/detalhe` | cursor, por bloco | sim | Acessos e alterações do profissional |
| GET | `/acessos` | offset | sim | Logs de acesso |
| GET | `/alteracoes` | offset (ou nenhuma, no drill-down) | sim (não no drill-down) | Logs de alteração |