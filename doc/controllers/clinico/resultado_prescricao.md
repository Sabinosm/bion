# Resultado da Prescrição — Controllers

Rotas do blueprint `resultado_prescricao` (`resultado_prescricao_controller.py`). Os caminhos são relativos ao prefixo com que o blueprint é registrado. Os controllers de medicamentos e de exames compartilham o mesmo formato de caminho (`/<uuid_resultado>/...`).

Respostas: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`, em que `erros` é `{campo: mensagem}` quando o erro pertence a campos. No erro de validação o `message` traz o texto curto (`campo: mensagem; ...`) e `erros` traz o detalhe por campo. Rotas auditadas devolvem a meta `NOOP` nos erros, para o erro não ser registrado como acesso com sucesso.

| Exceção | Status |
|---|---|
| `RecursoNaoEncontradoError` | 404 |
| `PermissaoNegadaError` | 403 |
| `DadosInvalidosError` / validação do schema | 422 |
| `ConflictoError` | 409 |

Empresa e usuário vêm sempre da sessão.

## Resumo das rotas

| Método | Rota | Papel | Auditoria | Descrição |
|---|---|---|---|---|
| POST | `/atendimento/<uuid_atendimento>` | Médico | Escrita | Cria o rascunho (modo manual) |
| GET | `/atendimento/<uuid_atendimento>` | Médico | Leitura | Lista os resultados do atendimento |
| GET | `/<uuid_resultado>` | Médico ou enfermeiro | Leitura | Detalhe com itens |
| GET | `/<uuid_resultado>/alertas` | Médico | — | Alertas de interação do conjunto atual |
| PATCH | `/<uuid_resultado>` | Médico | Escrita | Corrige o diagnóstico |
| POST | `/<uuid_resultado>/confirmar` | Médico | Escrita | Rascunho → confirmado |
| POST | `/<uuid_resultado>/descartar` | Médico | Exclusão lógica | Rascunho → descartado |

---

## `POST /atendimento/<uuid_atendimento>`

Registra, em rascunho, o diagnóstico (CID-10) e o desfecho de um atendimento em andamento.

- **Corpo:**

```json
{
  "codigo_cid10_principal": "A90",
  "descricao_cid10_principal": "Dengue clássica",
  "certeza_diagnostica": "provavel",
  "tipo_prescricao": "farmacologica"
}
```

- **Sucesso:** 201, "Resultado de prescrição registrado (rascunho).", `data` = resultado.
- **Erros:** 404 (atendimento); 403 (não é o dono); 409 (atendimento fora de andamento ou já há rascunho); 422 (corpo inválido, com `erros` por campo).

## `GET /atendimento/<uuid_atendimento>`

Resultados do atendimento, do mais antigo ao mais novo, com os itens. Só o médico dono; vale em qualquer status do atendimento.

- **Resposta:** lista de resultados (`to_dict()`).
- **Erros:** 404; 403 (não é o dono).

## `GET /<uuid_resultado>`

Detalhes de um resultado (com itens), só da própria empresa.

- **Resposta:** resultado (`to_dict()`).
- **Erros:** 404.

## `GET /<uuid_resultado>/alertas`

Alertas de interação medicamentosa do conjunto atual de medicamentos do resultado, entre si e com os medicamentos que o paciente já usa, mais a cobertura da base. O `escopo` da cobertura inclui `medicamentos_em_uso`.

- **Resposta:** `{ "alertas": [...], "cobertura": { "total_interacoes_na_base", "escopo", "aviso" } }`. Lista vazia **não** significa ausência de interação clínica.
- **Erros:** 404.

## `PATCH /<uuid_resultado>`

Corrige o diagnóstico do rascunho (só os campos enviados). Se algo mudou, a prescrição passa a ser do médico.

- **Corpo:** qualquer subconjunto de `codigo_cid10_principal`, `descricao_cid10_principal`, `certeza_diagnostica` e `tipo_prescricao` (este aceita `null`).
- **Sucesso:** 200, "Diagnóstico atualizado.", `data` = resultado.
- **Erros:** 404; 403 (não é o médico que o formulou); 409 (confirmado, descartado ou atendimento fora de andamento); 422 (nenhum campo enviado, campo obrigatório vazio ou fora do contrato).

## `POST /<uuid_resultado>/confirmar`

O médico responsável confirma a prescrição.

- **Corpo (opcional):** `{"reconhecer_alertas": true}` (booleano estrito; padrão `false`).
- **Sucesso:** 200, "Prescrição confirmada.", `data` = `{ "resultado": {...}, "alertas": [...], "cobertura": {...} }`.
- **Erros:** 404; 403; 409 (confirmado, descartado, atendimento fora de andamento, prescrição farmacológica sem medicamento, ou alertas de interação sem `reconhecer_alertas`); 422.

## `POST /<uuid_resultado>/descartar`

Descarta o rascunho (lógico: nada é apagado).

- **Corpo (opcional):** `{"motivo": "..."}` (até 255 caracteres).
- **Sucesso:** 200, "Prescrição descartada.", `data` = resultado.
- **Erros:** 404; 403; 409 (confirmado ou já descartado); 422. Vale mesmo com o atendimento finalizado ou cancelado.
