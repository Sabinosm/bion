# Prescrição de Exames — Controllers

Rotas do blueprint `prescricao_exame` (`prescricao_exame_controller.py`). Os caminhos são relativos ao prefixo com que o blueprint é registrado.

Respostas: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`, em que `erros` é `{campo: mensagem}` quando o erro pertence a campos. No erro de validação o `message` traz o texto curto e `erros` o detalhe por campo. Todas as rotas são auditadas, e o erro devolve a meta `NOOP`.

| Exceção | Status |
|---|---|
| `RecursoNaoEncontradoError` | 404 |
| `PermissaoNegadaError` | 403 |
| `DadosInvalidosError` / validação do schema | 422 |
| `ConflictoError` | 409 |

Todas exigem **médico**. Empresa e usuário vêm da sessão.

## Resumo das rotas

| Método | Rota | Auditoria | Descrição |
|---|---|---|---|
| POST | `/<uuid_resultado>/exames` | Escrita | Adiciona um exame ao rascunho |
| PATCH | `/<uuid_resultado>/exames/<uuid_item>` | Escrita | Altera urgência ou justificativa |
| DELETE | `/<uuid_resultado>/exames/<uuid_item>` | Escrita | Remove o exame do rascunho |

---

## `POST /<uuid_resultado>/exames`

Adiciona um exame prescrito ao rascunho do próprio médico (atendimento em andamento); o resultado passa a ser do médico.

- **Corpo:**

```json
{
  "uuid_exame": "00000000-0000-0000-0000-000000000000",
  "urgencia": "urgente",
  "justificativa": "Investigar quadro febril há 3 dias."
}
```

- **Sucesso:** 201, "Exame prescrito.", `data` = item.
- **Erros:** 404 (resultado inexistente; exame fora do catálogo); 403 (não é o médico que formulou); 409 (resultado confirmado ou descartado; atendimento fora de andamento; exame já consta na prescrição); 422 (corpo inválido, com `erros` por campo).

## `PATCH /<uuid_resultado>/exames/<uuid_item>`

Altera urgência ou justificativa (só o que foi enviado). Se algo mudou, o item e a prescrição passam a ser do médico.

- **Corpo:** `urgencia` (`rotina`, `urgente` ou `emergencia`; não aceita `null`) e/ou `justificativa` (`null` ou vazio limpa). Ao menos um campo.
- **Sucesso:** 200, "Exame atualizado.", `data` = item.
- **Erros:** 404 (resultado ou item); 403; 409; 422.

## `DELETE /<uuid_resultado>/exames/<uuid_item>`

Remove o exame do rascunho, inclusive sugestões da IA que o médico descartou.

- **Sucesso:** 200, "Exame removido da prescrição.". A meta de auditoria vai vazia.
- **Erros:** 404 (resultado ou item); 403; 409.
