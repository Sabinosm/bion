# Tipo Sanguíneo — Controllers

Rotas do módulo (`obs_tipo_sanguineo_controller.py`). `bp`, de leitura, sob o prefixo clínico (`/v1/api/pacientes/clinico`); `bp_escrita`, aninhado no atendimento, registrado com o **mesmo prefixo do blueprint de atendimento** (`/<uuid_atendimento>/pacientes/<uuid_paciente>/tipo-sanguineo`).

Respostas: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`. Exceções: 404, 403, 422, 409. Todas as rotas exigem **médico ou enfermeiro**. Não há rota de correção nem de remoção.

## Resumo das rotas

| Método | Rota | Descrição |
|---|---|---|
| GET | `/<uuid_paciente>/tipo-sanguineo` | Observação vigente |
| GET | `/<uuid_paciente>/tipo-sanguineo/historico` | Todas as observações |
| POST | `/<uuid_atendimento>/pacientes/<uuid_paciente>/tipo-sanguineo` | Registra uma observação |

## `GET /<uuid_paciente>/tipo-sanguineo`

- **Resposta:** observação vigente; `data` = `null` se nunca foi registrada.
- **Erros:** 404 (paciente).

## `GET /<uuid_paciente>/tipo-sanguineo/historico`

- **Resposta:** lista das observações, da mais recente para a mais antiga.
- **Erros:** 404.

## `POST /<uuid_atendimento>/pacientes/<uuid_paciente>/tipo-sanguineo`

- **Corpo:** `{"tipo_sanguineo": "O+"}`.
- **Sucesso:** 201, "Tipo sanguíneo registrado.", `data` = observação.
- **Erros:** 404 (atendimento ou paciente); 403 (não é o dono; enfermeiro fora da triagem); 409 (fora de andamento, paciente de outro atendimento, óbito, valor já vigente); 422 (valor fora da lista).
