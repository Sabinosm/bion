# Atendimento — Controllers

Rotas do blueprint `atendimento` (`controller.py`). Os caminhos são relativos ao prefixo com que o blueprint é registrado.

Respostas seguem o padrão do projeto: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`, em que `erros` é `{campo: mensagem}` quando o erro pertence a campos (a chave `_geral` é erro sem campo). Exceções `BionException` viram essa resposta com o status da própria exceção.

| Exceção | Status |
|---|---|
| `RecursoNaoEncontradoError` | 404 |
| `PermissaoNegadaError` | 403 |
| `DadosInvalidosError` | 422 |
| `ConflictoError` | 409 |

Todas as rotas passam a **empresa da sessão** ao service (o Atendimento herda a posse da Consulta e UUID sozinho não prova posse). O usuário e a função vêm da sessão, nunca do corpo.

## Resumo das rotas

| Método | Rota | Papel | Auditoria | Descrição |
|---|---|---|---|---|
| GET | `/` | Enfermeiro ou médico | — | Lista os Atendimentos da empresa |
| GET | `/<uuid>` | Enfermeiro ou médico | — | Atendimento com paciente e continuidade |
| GET | `/<uuid>/detalhe` | Enfermeiro ou médico | Leitura | Detalhe completo para exibição |
| GET | `/consulta/<uuid_consulta>` | Enfermeiro ou médico | — | Linha do tempo da Consulta |
| POST | `/consulta/<uuid_consulta>/abrir-triagem` | Enfermeiro ou médico | — | Abre uma triagem |
| POST | `/consulta/<uuid_consulta>/abrir-avaliacao-medica` | Médico | — | Abre uma avaliação médica |
| POST | `/consulta/<uuid_consulta>/abrir-reavaliacao` | Médico | — | Abre uma reavaliação |
| POST | `/<uuid_atendimento>/finalizar` | Enfermeiro ou médico (dono) | — | Finaliza o atendimento |
| POST | `/<uuid_atendimento>/cancelar` | Enfermeiro ou médico (dono) | — | Cancela o atendimento |

"Auditoria: Leitura" = `@acesso_auditado(operacao="leitura")`. Nas leituras auditadas que devolvem o par `(resposta, meta)`, o erro devolve `operacao: "NOOP"` para não ser registrado como leitura com sucesso.

---

## `GET /`

Lista os Atendimentos da empresa, do mais recente para o mais antigo.

- **Resposta:** lista de `Atendimento.to_dict()`.

## `GET /<uuid>`

Atendimento pelo UUID, com o bloco `paciente` e a continuidade.

- **Resposta:** `Atendimento.to_dict()` + `paciente` + `pode_continuar`, `proxima_acao`, `motivo_bloqueio`.
- **Auditoria:** registra o `uuid_paciente`.
- **Erros:** 404 se não existir ou for de outra empresa.

## `GET /<uuid>/detalhe`

Resumo completo de como foi (ou é) o atendimento, mesma fonte do PDF detalhado. Campos descritos em `atendimento.md`.

- **Acesso:** não exige ser o dono.
- **Auditoria:** leitura com `uuid_paciente`.
- **Erros:** 404.

## `GET /consulta/<uuid_consulta>`

Linha do tempo da Consulta em ordem cronológica.

- **Resposta:** lista de `Atendimento.to_dict()` + `profissional` (`uuid`, `nome_completo`, `funcao_clinica`).
- **Erros:** 404 se a Consulta não existir ou for de outra empresa.

## `POST /consulta/<uuid_consulta>/abrir-triagem`

Abre um Atendimento do tipo triagem. Sem corpo.

- **Sucesso:** 201, "Triagem aberta.", `data` = atendimento criado.
- **Erros:** 404 (Consulta); 409 (consentimento pendente, Consulta encerrada ou já há atendimento em andamento).

## `POST /consulta/<uuid_consulta>/abrir-avaliacao-medica`

Abre uma avaliação médica. Só médico. Não exige triagem prévia.

- **Sucesso:** 201, "Avaliação médica aberta.".
- **Erros:** os mesmos da triagem.

## `POST /consulta/<uuid_consulta>/abrir-reavaliacao`

Abre uma reavaliação (retorno do médico no mesmo episódio). Só médico.

- **Sucesso:** 201, "Reavaliação aberta.".
- **Erros:** os da triagem, mais 409 se a Consulta não estiver no status de reavaliação (`em-observacao`).

## `POST /<uuid_atendimento>/finalizar`

Finaliza um atendimento em andamento.

| Corpo (opcional) | Tipo | Descrição |
|---|---|---|
| `observacoes` | texto | Observações do profissional, gravadas no atendimento |

- **Sucesso:** 200, "Atendimento finalizado.", `data` = atendimento.
- **Erros:**
  - 404: atendimento inexistente ou de outra empresa.
  - 403: não é o dono; ou avaliação médica/reavaliação finalizada por quem não é médico.
  - 409: já finalizado ou cancelado; Consulta encerrada; binário incompleto; avaliação da IA em andamento; prescrição em rascunho.
  - 422: `observacoes` que não seja texto.

## `POST /<uuid_atendimento>/cancelar`

Cancela um atendimento em andamento. Não exige binário.

| Corpo (opcional) | Tipo | Descrição |
|---|---|---|
| `motivo_cancelamento` | texto | Um de `erro-abertura`, `paciente-nao-compareceu`, `paciente-recusou`, `transferencia`, `outro` |

- **Sucesso:** 200, "Atendimento cancelado.".
- **Erros:** 404; 403 (não é o dono); 409 (não está em andamento); 422 (motivo fora da lista).
