# Alergia — Controllers

Rotas do módulo de alergias (`alergia_controller.py`). Dois blueprints: `bp`, de leitura, sob o prefixo clínico dos pacientes (`/v1/api/pacientes/clinico`); e `bp_escrita`, aninhado no atendimento, que deve ser registrado com o **mesmo prefixo do blueprint de atendimento** (caminhos `/<uuid_atendimento>/pacientes/<uuid_paciente>/alergias...`).

Respostas: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`, com `erros` = `{campo: mensagem}` quando aplicável. Exceções: `RecursoNaoEncontradoError` 404, `PermissaoNegadaError` 403, `DadosInvalidosError` 422, `ConflictoError` 409.

Todas as rotas exigem **médico ou enfermeiro**. Empresa e usuário vêm da sessão.

## Resumo das rotas

| Método | Rota | Descrição |
|---|---|---|
| GET | `/<uuid_paciente>/alergias` | Alergias não removidas do paciente |
| POST | `/<uuid_atendimento>/pacientes/<uuid_paciente>/alergias` | Cria a alergia (com a primeira reação) |
| PUT | `.../alergias/<uuid_alergia>` | Atualiza código e confirmação |
| POST | `.../alergias/<uuid_alergia>/reacoes` | Registra uma nova reação |
| DELETE | `.../alergias/<uuid_alergia>` | Remove a alergia (ação sensível) |
| POST | `.../alergias/<uuid_alergia>/restaurar` | Reverte a remoção |
| DELETE | `.../alergias/reacoes/<uuid_reacao>` | Remove uma reação |

`...` = `/<uuid_atendimento>/pacientes/<uuid_paciente>`.

---

## `GET /<uuid_paciente>/alergias`

- **Resposta:** lista de alergias (`to_dict()`, com as reações).
- **Erros:** 404 (paciente).

## `POST .../alergias`

- **Corpo:**

```json
{
  "substancia": "Dipirona",
  "codigo_substancia": null,
  "flag_confirmado": false,
  "tipo_reacao": "cutanea",
  "gravidade": "leve",
  "descricao_reacao": "Urticária após uso."
}
```

- **Sucesso:** 201, "Alergia registrada.", `data` = alergia.
- **Erros:** 404 (atendimento ou paciente); 403 (não é o dono; enfermeiro fora da triagem); 409 (fora de andamento, paciente de outro atendimento, óbito, alergia ativa duplicada); 422 (corpo inválido).

## `PUT .../alergias/<uuid_alergia>`

- **Corpo:** `codigo_substancia` e/ou `flag_confirmado` (a substância não muda).
- **Sucesso:** 200, "Alergia atualizada.".
- **Erros:** 404 (alergia); 409 (alergia removida); os do guard.

## `POST .../alergias/<uuid_alergia>/reacoes`

- **Corpo:** `{"manifestacao": "respiratoria", "gravidade": "grave", "descricao": "...", "data_ocorrencia": "2026-10-01"}`.
- **Sucesso:** 201, "Reação registrada.", `data` = a alergia atualizada.
- **Erros:** 404 (alergia inexistente, removida ou de outro paciente); 422.

## `DELETE .../alergias/<uuid_alergia>`

Soft delete com motivo. **Ação sensível:** step-up e log atômico (a justificativa é a observação ou o motivo).

- **Corpo:** `{"motivo_delete": "registro-duplicado", "observacoes_delete": "..."}` (observação obrigatória com `outro`).
- **Sucesso:** 200, "Alergia removida.".
- **Erros:** 404 (alergia inexistente, de outro paciente ou já removida); 422 (motivo inválido).

## `POST .../alergias/<uuid_alergia>/restaurar`

- **Sucesso:** 200, "Alergia restaurada.".
- **Erros:** 409 (não está removida; já existe outra ativa à mesma substância).

## `DELETE .../alergias/reacoes/<uuid_reacao>`

Soft delete de uma reação registrada por engano. Mesmo corpo da remoção de alergia.

- **Sucesso:** 200, "Reação removida.".
- **Erros:** 404 (reação inexistente, de alergia removida ou de outro paciente); 422.
