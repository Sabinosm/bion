# Paciente — Controllers

Rotas dos blueprints de Paciente: `paciente_pessoal_controller.py` (cadastro e dados pessoais, sob `/v1/api/pacientes/pessoal`) e `paciente_clinico_controller.py` (prontuário, status e óbito, sob `/v1/api/pacientes/clinico`). Os caminhos abaixo são relativos a cada prefixo. A separação existe porque pessoal e clínico têm regras de permissão diferentes.

Respostas: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`, em que `erros` é `{campo: mensagem}` quando o erro pertence a campos. Rotas com auditoria devolvem a meta `NOOP` nos erros, para o erro não ser registrado como acesso com sucesso.

| Exceção | Status |
|---|---|
| `RecursoNaoEncontradoError` | 404 |
| `PermissaoNegadaError` | 403 |
| `DadosInvalidosError` | 422 |
| `ConflictoError` | 409 |

Toda rota passa a **empresa da sessão** ao service (o UUID sozinho não prova posse).

---

# Eixo pessoal — `/v1/api/pacientes/pessoal`

| Método | Rota | Quem | Auditoria | Descrição |
|---|---|---|---|---|
| GET | `/` | Logado | Leitura | Lista os pacientes da empresa |
| POST | `/` | Médico ou enfermeiro | — | Cadastra o paciente |
| GET | `/resumo` | Logado | — | Listagem enxuta e paginada |
| GET | `/<uuid>` | Admin, médico ou enfermeiro | Leitura | Dados cadastrais completos |
| PUT | `/<uuid>` | Admin, médico ou enfermeiro | — | Corrige o cadastro |
| POST | `/<uuid>/identificar` | Médico ou enfermeiro | — | Identifica um paciente de emergência |
| POST | `/<uuid>/anonimizar` | Admin | Ação sensível | Anonimiza (LGPD) |

## `GET /`

Pacientes da empresa. A PII só vem em texto claro (`pessoal`) para médico ou enfermeiro.

## `POST /`

Cadastro completo (regras e campos em `paciente.md`).

- **Sucesso:** 201, "Paciente cadastrado.", `data` = paciente com `pessoal`.
- **Erros:** 409 (CPF já cadastrado na empresa); 422 (corpo inválido, com `erros` por campo; CEP sem região).

## `GET /resumo`

Listagem enxuta (`to_dict_few`), 8 por página.

| Parâmetro (query) | Padrão | Descrição |
|---|---|---|
| `pagina` | `0` | Página (negativa vale 0) |
| `status`, `sexo_biologico` | — | Filtros |

Aberta a qualquer logado (decisão confirmada): nome e 4 dígitos do CPF servem para confirmar a identidade de quem já se apresentou. A busca `q` existe só na rota clínica.

## `GET /<uuid>`

Dados cadastrais completos, com PII e log de acesso. Não exige ser quem cadastrou.

- **Erros:** 404.

## `PUT /<uuid>`

Corrige o cadastro, só os campos enviados (`null` limpa os opcionais). Nunca escreve campos clínicos. Trocar o `cep` recalcula a região geográfica e o bairro do paciente.

- **Sucesso:** 200, "Dados pessoais atualizados.", `data` = paciente com `pessoal`.
- **Erros:** 404; 422 (corpo inválido; CEP novo sem região resolvida; paciente sem dados pessoais, com a orientação de usar `/identificar` quando for não identificado).

## `POST /<uuid>/identificar`

Completa o paciente de emergência com o mesmo corpo do cadastro.

- **Sucesso:** 200, "Paciente identificado.", `data` = paciente com `pessoal`.
- **Erros:** 404; 409 (falecido, já identificado, CPF já cadastrado); 422.

## `POST /<uuid>/anonimizar`

Direito ao esquecimento (LGPD): remove os dados pessoais e mantém o registro clínico anonimizado. **Só admin.** Irreversível: exige step-up e grava log atômico, com `justificativa` obrigatória (operação tratada como exclusão lógica).

- **Corpo:** `{"motivo": "..."}` (ou `"justificativa"`).
- **Sucesso:** 200, "Paciente anonimizado.", `data` = paciente (sem PII).
- **Erros:** 404; 422 (não identificado ou já anonimizado).

---

# Eixo clínico — `/v1/api/pacientes/clinico`

| Método | Rota | Quem | Auditoria | Descrição |
|---|---|---|---|---|
| GET | `/resumo` | Médico ou enfermeiro | — | Listagem enxuta com busca |
| GET | `/<uuid>` | Admin, médico ou enfermeiro | Leitura | Prontuário clínico completo |
| PUT | `/<uuid>` | Admin, médico ou enfermeiro | Admin: exceção | Altera o status clínico |
| POST | `/<uuid>/obito` | Admin, médico ou enfermeiro | Escrita | Registra o óbito |
| POST | `/<uuid>/obito/reverter` | Admin, médico ou enfermeiro | Ação sensível | Reverte o óbito |

Esta rota nunca devolve PII: só dado clínico do paciente.

## `GET /resumo`

Igual ao resumo pessoal, mais a busca `q`.

| Parâmetro (query) | Descrição |
|---|---|
| `q` | CPF completo (11 dígitos) ou parte do nome |
| `pagina`, `status`, `sexo_biologico` | Como no resumo pessoal |

## `GET /<uuid>`

Prontuário clínico **completo** (campos em `paciente.md`). Leitura pura: só log de acesso, sem step-up.

- **Erros:** 404.

## `PUT /<uuid>`

Altera só o `status`, entre `ativo` e `inativo`. Quando quem grava é o admin, a alteração e a linha de auditoria saem na mesma transação.

- **Corpo:** `{"status": "inativo"}`. Campos fora do contrato (`falecido`, `data_obito`, `status="obito"`) dão 422.
- **Sucesso:** 200, "Dados clínicos atualizados.", `data` = paciente (dado clínico).
- **Erros:** 404; 409 (paciente com óbito registrado); 422.

## `POST /<uuid>/obito`

Registra o óbito, mantendo `status`, `falecido` e `data_obito` sincronizados. Admin só como exceção (auditada).

- **Corpo:** `{"data_obito": "2026-10-30"}`.
- **Sucesso:** 200, "Óbito registrado.".
- **Erros:** 404; 409 (já falecido; consulta aberta); 422 (data ausente, futura, anterior ao nascimento ou mal formatada).

## `POST /<uuid>/obito/reverter`

Desfaz um óbito marcado por engano. **Ação sensível:** step-up, justificativa obrigatória e log atômico com a alteração.

- **Corpo:** `{"justificativa": "...", "status_destino": "ativo"}` (`status_destino`: `ativo`, padrão, ou `inativo`).
- **Sucesso:** 200, "Óbito revertido.".
- **Erros:** 404; 409 (não está com óbito); 422 (sem justificativa, ou destino inválido).
