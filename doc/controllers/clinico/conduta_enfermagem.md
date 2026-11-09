# Conduta de Enfermagem — Controllers

Rotas do blueprint `conduta_enfermagem` (`controller.py`). Devem ser registradas sob o **mesmo prefixo do binário**, o que expõe `/<uuid_atendimento>/pacientes/<uuid_paciente>/...`. Os caminhos abaixo são relativos a esse prefixo.

Respostas seguem o padrão do projeto: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`, em que `erros` é `{campo: mensagem}` quando o erro pertence a campos. Exceções `BionException` viram essa resposta com o status da própria exceção. Todas as rotas exigem enfermeiro ou médico (`@requer_papel_clinico("enfermeiro", "medico")`) e são auditadas; no erro a view devolve a meta `NOOP`. A empresa, o usuário e a função vêm da sessão.

## Resumo das rotas

| Método | Rota | Auditoria | Descrição |
|---|---|---|---|
| POST | `/<uuid_atendimento>/pacientes/<uuid_paciente>/condutas-enfermagem` | — | Registra uma conduta (insert-only) |
| GET | `/<uuid_atendimento>/condutas-enfermagem` | — | Condutas de um atendimento |
| GET | `/consulta/<uuid_consulta>/condutas-enfermagem` | — | Condutas da consulta inteira |

---

## `POST /<uuid_atendimento>/pacientes/<uuid_paciente>/condutas-enfermagem`

Registra uma conduta de enfermagem no atendimento de triagem em andamento.

- **Corpo:**

```json
{
  "descricao_conduta": "Orientado repouso e hidratação; reavaliar sinais em 30 minutos.",
  "uuid_protocolo_catalogo": "00000000-0000-0000-0000-000000000000"
}
```

| Campo | Tipo | Regra |
|---|---|---|
| `descricao_conduta` | texto | Obrigatório; 3 a 2000 caracteres |
| `uuid_protocolo_catalogo` | texto | Opcional; 36 caracteres |

- **Sucesso:** 201, "Conduta de enfermagem registrada.", `data` = conduta criada. A meta de auditoria registra `id_registro` da conduta e `uuid_registro` do atendimento.
- **Erros** (meta de auditoria `NOOP`):
  - 422, corpo inválido: "Dados inválidos." com `erros` por campo, vindos da validação do schema.
  - 404: atendimento ou paciente inexistente na empresa.
  - 403: não é o dono do atendimento.
  - 409: paciente de outro atendimento; atendimento fora de andamento; tipo diferente de triagem; paciente com óbito.
  - 422: protocolo do catálogo inexistente.

## `GET /<uuid_atendimento>/condutas-enfermagem`

Lista as condutas de um atendimento, em ordem cronológica crescente.

- **Resposta:** lista de condutas (`to_dict()`).
- **Erros:** 404 se o atendimento não existir ou for de outra empresa.

## `GET /consulta/<uuid_consulta>/condutas-enfermagem`

Lista as condutas de todos os atendimentos de uma Consulta, em ordem cronológica crescente. É como o médico lê, na avaliação, o que a triagem fez.

- **Resposta:** lista de condutas (`to_dict()`).
- **Erros:** 404 se a Consulta não existir ou for de outra empresa.
