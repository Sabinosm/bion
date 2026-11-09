# Dados Clínicos — Controllers

Rotas do blueprint `dados_clinicos` (`controller.py`). Devem ser registradas sob o **mesmo prefixo** das rotas de alergia e do binário, o que expõe `/<uuid_atendimento>/pacientes/<uuid_paciente>/...`. Os caminhos abaixo são relativos a esse prefixo.

Todas as rotas exigem médico ou enfermeiro (`@requer_papel_clinico("medico", "enfermeiro")`) e são auditadas. A empresa, o usuário e a função vêm da sessão (o controller monta um `AutorClinico`) e nunca do corpo.

Respostas: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`, em que `erros` é `{campo: mensagem}` quando o erro pertence a campos. No erro a view devolve a meta de auditoria `NOOP`, para o erro não ser registrado como acesso com sucesso.

| Exceção | Status |
|---|---|
| `RecursoNaoEncontradoError` | 404 |
| `PermissaoNegadaError` | 403 |
| `DadosInvalidosError` | 422 |
| `ConflictoError` | 409 |

## Resumo das rotas

| Método | Rota | Auditoria | Descrição |
|---|---|---|---|
| POST | `/<uuid_atendimento>/pacientes/<uuid_paciente>/sinais-vitais` | — | Registra um lote de sinais vitais |
| POST | `.../coleta-clinica` | — | Cria uma coleta clínica |
| POST | `.../coleta-clinica/<uuid_coleta>/input-protocolo` | — | Registra o input de protocolo |
| POST | `.../protocolos/<uuid_protocolo>/executar` | — | Executa o protocolo sobre o input vigente |
| GET | `.../protocolos-disponiveis` | — | Protocolos que o atendimento pode usar |
| GET | `.../protocolos/<uuid_protocolo>/estrutura` | — | Campos do protocolo |

`...` = `/<uuid_atendimento>/pacientes/<uuid_paciente>`. As rotas antigas (`/<uuid_atendimento>/sinais-vitais`, `/<uuid_atendimento>/coleta-clinica` e `/coleta-clinica/<uuid_coleta>/input-protocolo`) **deixaram de existir**: não passavam pelo guard.

---

## `POST .../sinais-vitais`

Registra um ou mais sinais vitais. Não exige binário.

- **Corpo:** `{"sinais": [ { "tipo_parametro": "spo2", "valor_numerico": 96, "unidade": "%" } ]}` — de 1 a 50 itens (regras em `dados_clinicos.md`).
- **Sucesso:** 201, "Sinais vitais registrados.", `data` = lista dos sinais gravados.
- **Erros:** 404 (atendimento ou paciente), 403 (não é o dono; enfermeiro fora da triagem), 409 (fora de andamento, paciente de outro atendimento, óbito), 422 (corpo inválido, com `erros` por campo; tipo de parâmetro não mapeado na tabela LOINC).

## `POST .../coleta-clinica`

Cria uma coleta clínica. Exige o binário completo.

- **Corpo:** `{"desde_quando_sintomas": 6}` (horas, opcional, 0 a 32767).
- **Sucesso:** 201, "Coleta clínica registrada.", `data` = coleta.
- **Erros:** os do guard, mais 409 se o binário estiver incompleto; 422 para corpo inválido.

## `POST .../coleta-clinica/<uuid_coleta>/input-protocolo`

Registra o input de protocolo de uma coleta **deste** atendimento. Insert-only: reenviar cria outro, e o último é o vigente.

- **Corpo:**

```json
{
  "input_json": { "freq_respiratoria": 18, "nivel_consciencia": "alerta" },
  "queixa_principal": "Dor torácica há 2 horas",
  "valor_avpu": "A"
}
```

  `tipo_input` é opcional (se vier, igual ao tipo do atendimento). É preciso informar ao menos um de `input_json`, `queixa_principal` e `valor_avpu`.
- **Sucesso:** 201, "Input de protocolo registrado.", `data` = input.
- **Erros:** os do guard; 409 (binário incompleto; tipo de atendimento sem input de protocolo); 404 (coleta inexistente ou de outro atendimento); 422 (corpo inválido; `tipo_input` diferente do atendimento).

## `POST .../protocolos/<uuid_protocolo>/executar`

Executa o protocolo sobre o input vigente. **Idempotente:** se o protocolo já foi executado neste input, devolve a execução existente.

- **Corpo:** nenhum. As respostas vêm do input vigente.
- **Sucesso:**
  - 201, "Protocolo executado.", `data` = execução nova.
  - 200, "Protocolo já executado neste input; resultado existente.", `data` = a execução existente.
- **Erros:**
  - 404: atendimento, paciente ou protocolo inexistente.
  - 403: não é o dono; enfermeiro fora da triagem.
  - 409: tipo de atendimento sem protocolo; binário incompleto; protocolo inativo, de escopo incompatível ou não liberado pela instituição; tipo de protocolo sem execução; nenhum input registrado.
  - 422: respostas inválidas; `erros` e a mensagem vêm da validação da família do protocolo.

## `GET .../protocolos-disponiveis`

Lista o catálogo que o atendimento pode usar, com favoritos primeiro.

- **Resposta:** lista de itens com os dados do catálogo e `liberado_pela_empresa`, `politica`, `padrao_institucional`, `favorito`, `default_pessoal`.
- **Erros:** 404 se o atendimento não existir ou for de outra empresa.

## `GET .../protocolos/<uuid_protocolo>/estrutura`

Campos do protocolo, para montar o formulário do input.

- **Resposta:** `uuid`, `nome_protocolo`, `sigla`, `tipo_resultado`, `explicacao_json` e `campos` (`campo`, `texto`, `label`, `tipo_campo`, `opcoes`, `obrigatorio`).
- **Erros:** 404 (atendimento ou protocolo); 409 (protocolo inativo, de escopo incompatível, não liberado ou de tipo sem estrutura).
