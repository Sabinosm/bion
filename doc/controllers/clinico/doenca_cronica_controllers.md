# Doença Crônica — Controllers

Rotas do módulo (`doenca_cronica_controller.py`). `bp`, de leitura, sob o prefixo clínico (`/v1/api/pacientes/clinico`); `bp_escrita`, aninhado no atendimento, registrado com o **mesmo prefixo do blueprint de atendimento** (`/<uuid_atendimento>/pacientes/<uuid_paciente>/doencas-cronicas...`).

Respostas: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`. Exceções: 404, 403, 422 e 409 (`RecursoNaoEncontradoError`, `PermissaoNegadaError`, `DadosInvalidosError`, `ConflictoError`). Todas as rotas exigem **médico ou enfermeiro**.

## Resumo das rotas

| Método | Rota | Descrição |
|---|---|---|
| GET | `/<uuid_paciente>/doencas-cronicas` | Doenças vigentes |
| GET | `/<uuid_paciente>/doencas-cronicas/historico` | Vigentes e encerradas por revisão |
| POST | `/<uuid_atendimento>/pacientes/<uuid_paciente>/doencas-cronicas` | Registra uma doença |
| PUT | `.../doencas-cronicas/<uuid_doenca>` | Atualiza só `observacoes` |
| POST | `.../doencas-cronicas/<uuid_doenca>/revisar` | Fecha a vigente e cria a nova |
| DELETE | `.../doencas-cronicas/<uuid_doenca>` | Remove (ação sensível) |
| POST | `.../doencas-cronicas/<uuid_doenca>/restaurar` | Reverte a remoção |

`...` = `/<uuid_atendimento>/pacientes/<uuid_paciente>`.

---

## `GET /<uuid_paciente>/doencas-cronicas` e `/historico`

- **Resposta:** lista de doenças (`to_dict()`); o histórico traz também as encerradas por revisão, da mais antiga para a mais recente, sem as removidas.
- **Erros:** 404 (paciente).

## `POST .../doencas-cronicas`

- **Corpo:**

```json
{
  "codigo_cid10": "E11.9",
  "descricao_cid10": "Diabetes mellitus tipo 2",
  "desde": "2020-03-01",
  "status": "ativa",
  "observacoes": "Em uso de metformina."
}
```

- **Sucesso:** 201, "Doença crônica registrada.".
- **Erros:** 404; 403; 409 (fora de andamento, óbito, CID já vigente); 422.

## `PUT .../doencas-cronicas/<uuid_doenca>`

- **Corpo:** `{"observacoes": "..."}` (ou `null` para limpar). Qualquer outro campo dá 422 com a orientação de usar `/revisar`.
- **Sucesso:** 200, "Doença crônica atualizada.".
- **Erros:** 404; 409 (removida ou encerrada por revisão); 422.

## `POST .../doencas-cronicas/<uuid_doenca>/revisar`

- **Corpo:** ao menos um de `codigo_cid10` + `descricao_cid10` (juntos), `desde` e `status`; `observacoes` opcional.
- **Sucesso:** 201, "Doença crônica revisada.", `data` = a **nova** linha.
- **Erros:** 404; 409 (removida, já encerrada, novo CID duplicado); 422 (nenhuma mudança real, ou corpo inválido).

## `DELETE .../doencas-cronicas/<uuid_doenca>`

Soft delete com motivo. **Ação sensível:** step-up e log atômico.

- **Corpo:** `{"motivo_delete": "erro-digitacao", "observacoes_delete": "..."}`.
- **Sucesso:** 200, "Doença crônica removida.".
- **Erros:** 404 (inexistente, de outro paciente ou já removida); 409 (encerrada por revisão); 422.

## `POST .../doencas-cronicas/<uuid_doenca>/restaurar`

- **Sucesso:** 200, "Doença crônica restaurada.".
- **Erros:** 409 (não está removida; CID já vigente em outra linha).
