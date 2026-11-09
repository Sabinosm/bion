# Consentimento LGPD — Controllers

Dois blueprints, ambos sob `/v1/api/pacientes/lgpd`: `lgpd_controller.py` (fluxo manual) e `consentimento_digital_controller.py` (assinatura por QR code). A rota de anonimizar **não** mora aqui: está em `paciente_pessoal_controller.py`.

Respostas: sucesso `{"status": "success", "message", "data"}`; erro `{"status": "error", "message", "erros"}`. Exceções: 404, 403, 422, 409. Rotas auditadas devolvem a meta `NOOP` nos erros. Empresa e usuário vêm da sessão.

---

# Fluxo manual — `lgpd_controller.py`

| Método | Rota | Quem | Auditoria | Descrição |
|---|---|---|---|---|
| GET | `/<uuid_paciente>/consentimentos` | Logado | — | Histórico de consentimentos |
| POST | `/<uuid_paciente>/consentimentos` | Médico ou enfermeiro | Escrita | Registro manual |
| POST | `/<uuid_paciente>/consentimentos/revogar` | Médico ou enfermeiro | Ação sensível | Revoga o ativo |
| POST | `/<uuid_paciente>/consentimentos/dispensar-emergencia` | Médico ou enfermeiro | Escrita | Dispensa por emergência |

## `GET /<uuid_paciente>/consentimentos`

- **Resposta:** lista de consentimentos (`to_dict()`).
- **Erros:** 404.

## `POST /<uuid_paciente>/consentimentos`

- **Corpo:**

```json
{
  "versao_termo": "lgpd-v1.0-2026",
  "canal_coleta": "presencial-papel",
  "escopo_consentimento": { "escopo": ["apoio_ia"] },
  "hash_documento": null
}
```

- **Sucesso:** 201, "Consentimento registrado.", `data` = consentimento. A auditoria registra o `uuid_paciente`.
- **Erros:** 404; 409 (outro consentimento ativo sendo registrado ao mesmo tempo); 422 (corpo inválido; canal `presencial-digital`; escopo desconhecido).

## `POST /<uuid_paciente>/consentimentos/revogar`

**Ação sensível:** step-up e log atômico.

- **Corpo:** `{"motivo": "Paciente retirou o consentimento."}`.
- **Sucesso:** 200, "Consentimento revogado.".
- **Erros:** 404 (paciente ou nenhum consentimento ativo); 422 (motivo ausente ou inválido).

## `POST /<uuid_paciente>/consentimentos/dispensar-emergencia`

Dispensa por urgência ou emergência (LGPD art. 11, II, "f"). Não bloqueia nem desbloqueia nada: deixa rastreável que a coleta normal foi pulada de propósito, com motivo e responsável.

- **Corpo:** `{"motivo": "Paciente inconsciente na chegada."}`.
- **Sucesso:** 201, "Consentimento dispensado por emergência.".
- **Erros:** 404; 422.

---

# Assinatura digital — `consentimento_digital_controller.py`

## Rotas públicas (o token é a autenticação)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/assinar/<token>` | Dados para montar a tela |
| GET | `/assinar/<token>/termo.pdf` | Termo em PDF |
| POST | `/assinar/<token>` | Registra a assinatura |
| GET | `/assinar/<token>/comprovante.pdf` | Cópia assinada para o paciente (janela curta) |

Não têm usuário logado nem rate limit hoje; a trilha é a própria sessão (IP, user-agent, horário) e o consentimento criado.

### `GET /assinar/<token>`

- **Resposta:** `token`, `paciente_nome`, `paciente_cpf` (mascarado), `escopos_disponiveis` (`codigo` e `descricao`), `versao_termo`, `texto_termo`, `hash_pdf_original`, `termo_pdf_url`, `expira_em`, `unidade_id`.
- **Erros:** 404 (token); 409 (link já usado); 422 (link expirado).

### `GET /assinar/<token>/termo.pdf`

PDF do termo, só enquanto o link está pendente. O cabeçalho `X-SHA256` traz o hash do PDF (o mesmo `hash_pdf_original` da tela).

### `POST /assinar/<token>`

- **Corpo:**

```json
{
  "confirmo_identidade": true,
  "declaro_consentimento": true,
  "assinatura_canvas": "data:image/png;base64,...",
  "hash_pdf_original": "<sha256 recebido no GET>",
  "user_agent": "(opcional; o do servidor tem prioridade)",
  "geolocalizacao": "São Paulo, SP",
  "geo_divergente": false,
  "escopos_selecionados": ["pesquisa"]
}
```

- **Sucesso:** 201, "Consentimento assinado com sucesso.", `data` = `consentimento_uuid`, `hash_pdf_final`, `data_consentimento`, `download_url`, `copia_valida_ate`.
- **Erros:** 404 (token); 409 (já usado); 422 (corpo inválido, hash que não confere, assinatura que não é PNG, link expirado).

### `GET /assinar/<token>/comprovante.pdf`

Cópia assinada para o paciente, logo após assinar, por tempo limitado (`CONSENT_JANELA_COPIA_MIN`). Cabeçalho `Cache-Control: no-store` (contém nome, CPF e assinatura). Todo caso inválido responde 404 igual.

## Rotas protegidas (médico ou enfermeiro)

| Método | Rota | Auditoria | Descrição |
|---|---|---|---|
| POST | `/<uuid_paciente>/gerar-link-assinatura` | — | Gera o link de assinatura |
| GET | `/assinatura/<token>/status` | — | Estado do link (polling) |
| POST | `/assinatura/<token>/cancelar` | — | Invalida um link pendente |
| GET | `/comprovante/<uuid_consentimento>` | Leitura | Metadados do comprovante |
| GET | `/download-pdf/<uuid_consentimento>` | Exportação | PDF assinado |

### `POST /<uuid_paciente>/gerar-link-assinatura`

- **Corpo (opcional):** `{"versao_termo": "lgpd-v1.0-2026"}` (sem ele usa a vigente).
- **Sucesso:** 201, `data` = `token`, `url_assinatura`, `expira_em`, `paciente_nome`, `paciente_cpf`.
- **Erros:** 404 (paciente ou empresa); 422 (versão inválida, paciente sem dados pessoais, cadastro da empresa incompleto).

### `GET /assinatura/<token>/status`

Polling do front do médico. Sem auditoria: é consulta repetida de estado.

- **Resposta:** `status` (`pendente`, `usado` ou `expirado`) e `expira_em`; quando `usado`, também `usado_em` e `consentimento_uuid`.

### `POST /assinatura/<token>/cancelar`

- **Sucesso:** 200, "Link cancelado.", `data` = `{"status": "expirado"}`.
- **Erros:** 404; 409 (o link já foi utilizado).

### `GET /comprovante/<uuid_consentimento>`

Metadados do comprovante, sem IP, user-agent nem caminhos internos.

- **Resposta:** `uuid`, `versao_termo`, `data_consentimento`, `canal_coleta`, `status`, `hash_documento`, `escopo`, `pdf_url`.
- **Erros:** 404.

### `GET /download-pdf/<uuid_consentimento>`

PDF assinado, refeito em memória a partir do banco (recebe o UUID do consentimento, nunca um caminho; o service confere a empresa). Cabeçalhos: `Cache-Control: no-store` e `X-Integridade` (`confere` ou `divergente`).

- **Erros:** 404 (inexistente, de outra empresa, ou PDF não disponível).
