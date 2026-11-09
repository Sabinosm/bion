# Medicamento em Uso — Controllers

Rotas do módulo (`medicamentos_em_uso_controller.py`). `bp`, de leitura, sob o prefixo clínico (`/v1/api/pacientes/clinico`); `bp_escrita`, aninhado no atendimento (registrar com `url_prefix="/atendimentos"`, o mesmo do atendimento): `/<uuid_atendimento>/pacientes/<uuid_paciente>/medicamentos-em-uso...`.

Respostas: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`. Exceções: 404, 403, 422, 409. Todas as rotas exigem **médico ou enfermeiro**.

Os erros de negócio são tratados por um wrapper **por fora** dos decorators de auditoria: sob a ação sensível a view não devolve o erro (o decorator não acharia `id_registro`); deixa a exceção subir, o decorator desfaz a transação, e a resposta de erro sai depois com a mesma mensagem, status e `erros`.

## Resumo das rotas

| Método | Rota | Auditoria | Descrição |
|---|---|---|---|
| GET | `/<uuid_paciente>/medicamentos-em-uso` | — | Lista do paciente |
| GET | `/<uuid_paciente>/medicamentos-em-uso/interacoes` | — | Interações dos ativos |
| POST | `/<uuid_atendimento>/pacientes/<uuid_paciente>/medicamentos-em-uso` | — | Registra um medicamento |
| POST | `.../medicamentos-em-uso/<uuid_medicamento>/substituir` | — | Troca dose ou frequência |
| POST | `.../medicamentos-em-uso/<uuid_medicamento>/encerrar` | — | Fecha o tratamento |
| DELETE | `.../medicamentos-em-uso/<uuid_medicamento>` | Ação sensível | Remove |
| POST | `.../medicamentos-em-uso/<uuid_medicamento>/restaurar` | Ação sensível | Reverte a remoção |

`...` = `/<uuid_atendimento>/pacientes/<uuid_paciente>`.

---

## `GET /<uuid_paciente>/medicamentos-em-uso`

Medicamentos não removidos do paciente, ativos primeiro (mais recentes antes).

| Parâmetro (query) | Descrição |
|---|---|
| `ativos` | `true`, `1` ou `sim` devolve só os ativos |

- **Erros:** 404 (paciente).

## `GET /<uuid_paciente>/medicamentos-em-uso/interacoes`

Cruza os ativos com o catálogo de interações.

- **Resposta:** `{ "interacoes": [...], "nao_verificados": [...], "cobertura": {...} }` (ver `medicamento_em_uso.md`).

## `POST .../medicamentos-em-uso`

- **Corpo:**

```json
{
  "uuid_catalogo": "00000000-0000-0000-0000-000000000000",
  "dose": "500 mg",
  "frequencia": "12/12 horas",
  "desde": "2025-01-10"
}
```

- **Sucesso:** 201, "Medicamento em uso registrado.", `data` = `{ "medicamento": {...}, "alertas_interacao": {...} }`.
- **Erros:** 404 (atendimento ou paciente); 403; 409 (fora de andamento, óbito, medicamento já ativo); 422 (corpo inválido; `uuid_catalogo` inexistente; sem descrição).

## `POST .../medicamentos-em-uso/<uuid_medicamento>/substituir`

- **Corpo:** ao menos um de `descricao`, `dose`, `frequencia`; `data_mudanca` opcional.
- **Sucesso:** 201, "Medicamento em uso substituído.", `data` = registro novo.
- **Erros:** 404; 409 (removido ou já encerrado); 422 (sem alteração real, data anterior ao início do uso).

## `POST .../medicamentos-em-uso/<uuid_medicamento>/encerrar`

- **Corpo:** `{"status_uso": "interrompido" | "concluido", "ate": "2026-10-30"}` (`ate` opcional).
- **Sucesso:** 200, "Medicamento em uso encerrado.".
- **Erros:** 404; 409; 422.

## `DELETE .../medicamentos-em-uso/<uuid_medicamento>`

Soft delete com motivo. **Ação sensível:** step-up e log atômico (a justificativa junta motivo e observações).

- **Corpo:** `{"motivo_delete": "registro-duplicado", "observacoes_delete": "..."}`.
- **Sucesso:** 200, "Medicamento em uso removido.".
- **Erros:** 404 (inexistente, de outro paciente ou já removido); 422.

## `POST .../medicamentos-em-uso/<uuid_medicamento>/restaurar`

Reverte o soft delete. **Ação sensível.**

- **Sucesso:** 200, "Medicamento em uso restaurado.".
- **Erros:** 404; 409 (não está removido; já existe outro ativo do mesmo medicamento).
