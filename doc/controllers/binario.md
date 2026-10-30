# Binário — Controllers

Rotas do blueprint `binario` (`binario_controller.py`). Devem ser registradas sob o **mesmo prefixo** das rotas de escrita de alergia e de conduta de enfermagem, o que expõe `/<uuid_atendimento>/pacientes/<uuid_paciente>/...`. Os caminhos abaixo são relativos a esse prefixo.

Respostas seguem o padrão do projeto: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`, em que `erros` é `{campo: mensagem}` quando o erro pertence a campos (a chave `_geral` é erro sem campo). Exceções `BionException` viram essa resposta com o status da própria exceção (404, 403, 422 e 409 conforme o caso). Todas as rotas são auditadas; no erro a view devolve a meta `NOOP`, para o erro não ser registrado como acesso com sucesso.

A empresa, o usuário e a função clínica vêm da sessão; as rotas de escrita montam um `AutorClinico` e nunca confiam no corpo.

## Resumo das rotas

| Método | Rota | Acesso | Auditoria | Descrição |
|---|---|---|---|---|
| GET | `/<uuid_atendimento>/binario` | Médico ou enfermeiro | Leitura | Estado de conferência das seções |
| GET | `/<uuid_atendimento>/binario/do-paciente` | Médico ou enfermeiro | Leitura | Binário montado dos registros do paciente |
| POST | `/<uuid_atendimento>/pacientes/<uuid_paciente>/binario` | Médico ou enfermeiro | Escrita | Confere as 4 seções (agregada) |
| POST | `/<uuid_atendimento>/pacientes/<uuid_paciente>/binario/<secao>` | Médico ou enfermeiro | Escrita | Confere uma seção (granular) |

"Médico ou enfermeiro" = `@requer_papel_clinico("medico", "enfermeiro")`. A empresa vem da sessão.

---

## `GET /<uuid_atendimento>/binario`

Estado de cada seção, com os registros ativos do paciente como pré-preenchimento nas pendentes.

- **Resposta:** `uuid_atendimento`, `completo`, `pendentes` e `secoes` (ver `binario.md`).
- **Erros:** 404 se o atendimento não existir ou for de outra empresa.

## `GET /<uuid_atendimento>/binario/do-paciente`

Binário no formato do corpo da rota agregada, a partir dos registros ativos e da última conferência confirmada. Só leitura.

- **Resposta:** `uuid_atendimento`, `binario`, `confirmacao`, `pendentes`, `completo`.
- **Erros:** 404.

## `POST /<uuid_atendimento>/pacientes/<uuid_paciente>/binario`

Confere as **quatro seções de uma vez**, atomicamente. Todas são obrigatórias.

- **Corpo (`BinarioIn`):**

```json
{
  "alergias":       { "possui": true,  "nao_foi_possivel_coletar": false, "itens": [ { } ] },
  "medicamentos":   { "possui": false },
  "tipo_sanguineo": { "possui": true,  "tipo_sanguineo": "O+" },
  "doenca_cronica": { "possui": false, "nao_foi_possivel_coletar": true }
}
```

| Campo da seção | Tipo | Descrição |
|---|---|---|
| `possui` | booleano, obrigatório | O paciente tem o dado |
| `nao_foi_possivel_coletar` | booleano, padrão `false` | Seção não coletada; força `possui=false` e não aceita itens |
| `itens` | lista de até 50 objetos | Alergias, medicamentos e doenças crônicas, no formato dos schemas de criação de cada dado |
| `tipo_sanguineo` | texto de até 20 caracteres | Só na seção do tipo sanguíneo |

Campos extras são recusados.

- **Sucesso:** 201, "Binário conferido.", `data` = `{ "conferidas": [...], "binario": {...} }`.
- **Erros:**
  - 404: atendimento ou paciente inexistente na empresa.
  - 403: não é o dono; enfermeiro fora da triagem.
  - 409: seção já conferida; atendimento fora de andamento; paciente de outro atendimento ou com óbito; "não possui" com registro ativo; registro duplicado.
  - 422: corpo inválido (erros por campo); `possui=true` sem item e sem registro ativo; tipo sanguíneo com `possui=false`.

## `POST /<uuid_atendimento>/pacientes/<uuid_paciente>/binario/<secao>`

Confere **uma seção**, pelo mesmo caminho do agregado.

- **Parâmetro de caminho:** `secao` = `alergias`, `medicamentos`, `tipo_sanguineo` ou `doenca_cronica`.
- **Corpo:** o schema da seção (`possui`, `nao_foi_possivel_coletar` e `itens` ou `tipo_sanguineo`).
- **Sucesso:** 201, "Seção do binário conferida.", `data` = `{ "conferidas": [...], "binario": {...} }`.
- **Erros:** os da rota agregada, mais 404 para seção inexistente.
