# Prescrição — Controllers

Rotas do blueprint `prescricao` (`prescricao_controller.py`): medicamentos prescritos. Os caminhos são relativos ao prefixo com que o blueprint é registrado.

Respostas: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`, em que `erros` é `{campo: mensagem}` quando o erro pertence a campos. No erro de validação o `message` traz o texto curto (`campo: mensagem; ...`) e `erros` o detalhe por campo. Todas as rotas são auditadas, e o erro devolve a meta `NOOP`, para não ser registrado como acesso com sucesso.

| Exceção | Status |
|---|---|
| `RecursoNaoEncontradoError` | 404 |
| `PermissaoNegadaError` | 403 |
| `DadosInvalidosError` / validação do schema | 422 |
| `ConflictoError` | 409 |

Todas exigem **médico** (`@requer_papel_clinico("medico")`). Empresa e usuário vêm da sessão.

## Resumo das rotas

| Método | Rota | Auditoria | Descrição |
|---|---|---|---|
| POST | `/<uuid_resultado>/medicamentos` | Escrita | Adiciona um medicamento ao rascunho |
| PATCH | `/<uuid_resultado>/medicamentos/<uuid_item>` | Escrita | Altera dose, frequência, duração ou orientações |
| DELETE | `/<uuid_resultado>/medicamentos/<uuid_item>` | Escrita | Remove o medicamento do rascunho |

---

## `POST /<uuid_resultado>/medicamentos`

Adiciona um medicamento (por `uuid_catalogo`) ao rascunho do médico; o resultado passa a ser do médico.

- **Corpo:**

```json
{
  "uuid_catalogo": "00000000-0000-0000-0000-000000000000",
  "dose": "500 mg",
  "frequencia": "8/8 horas",
  "duracao": "5 dias",
  "orientacoes": "Tomar após as refeições."
}
```

| Campo | Regra |
|---|---|
| `uuid_catalogo` | Obrigatório (UUID) |
| `dose`, `frequencia`, `duracao` | Opcionais, até 100 caracteres |
| `orientacoes` | Opcional, até 2000 caracteres |

- **Sucesso:** 201, "Medicamento prescrito.", `data` = `{ "prescricao": {...}, "alertas": [...], "cobertura": {...} }` (alertas do conjunto atual do rascunho, entre si e com os medicamentos que o paciente já usa).
- **Erros:**
  - 404: resultado inexistente na empresa; medicamento fora do catálogo.
  - 403: não é o médico que formulou o resultado.
  - 409: resultado confirmado ou descartado; atendimento fora de andamento; medicamento já consta na prescrição.
  - 422: corpo inválido, com `erros` por campo.

## `PATCH /<uuid_resultado>/medicamentos/<uuid_item>`

Altera só o que foi enviado; `null` ou vazio limpa o campo. Se algo mudou, o item e a prescrição passam a ser do médico.

- **Corpo:** qualquer subconjunto de `dose`, `frequencia`, `duracao` e `orientacoes` (ao menos um campo).
- **Sucesso:** 200, "Medicamento atualizado.", `data` = item.
- **Erros:** 404 (resultado ou item); 403; 409; 422 (nenhum campo enviado ou fora do contrato).

## `DELETE /<uuid_resultado>/medicamentos/<uuid_item>`

Remove o medicamento do rascunho, inclusive sugestões da IA que o médico descartou.

- **Sucesso:** 200, "Medicamento removido da prescrição.". A meta de auditoria vai vazia.
- **Erros:** 404 (resultado ou item); 403; 409.
