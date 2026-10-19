# Controllers de Autenticação

Rotas HTTP do domínio Auth. Cada arquivo registra o próprio blueprint; o prefixo das URLs depende de como os blueprints são registrados na aplicação, então os caminhos abaixo são relativos a cada blueprint.

Para o funcionamento interno (estados da sessão, limites de tentativas, step-up), ver `auth_fluxo.md`.

---

# Convenções gerais

## Exigência de sessão por rota

| Marcador | Significa |
|---|---|
| Pública | Não exige sessão |
| Sessão completa | Usuário autenticado e sem pendências (`@requer_login`) |
| Sessão completa ou onboarding | Aceita também quem está no onboarding (`@requer_login_ou_onboarding_pendente`) |
| Onboarding | Só quem está com `onboarding_pendente` (`@onboarding_pendente_required`) |
| MFA pendente | Só quem passou pelo primeiro fator e aguarda o segundo (`@mfa_pendente_required`) |

No onboarding, as rotas de cadastro de fator (`/registrar/*` de WebAuthn e TOTP) só aceitam usuário sem fator confirmado ou que já cadastrou um nesta sessão.

## Formato das respostas

| Origem | Formato |
|---|---|
| Login, logout, `/me` | Envelope padrão `json_success(data=..., message=...)` |
| Demais rotas | JSON direto (`jsonify`), sem envelope |
| Callbacks do Google | Redirect para o frontend (`FRONTEND_URL`) |

## Vocabulário recorrente

| Termo | Descrição |
|---|---|
| `acao` | Identificador da ação sensível protegida pelo step-up (ex.: `excluir_prontuario`) |
| `metodo` | `webauthn`, `totp` ou `senha_google` |
| `tentativas_restantes` | Tentativas que ainda restam no limite do método atual |

---

# Login e sessão (`login.py`, blueprint `auth`)

## `POST /login`

Autentica por login e senha, reinicia a sessão e a deixa pendente de 2FA. Pública.

| Campo (JSON ou form) | Obrigatório | Descrição |
|---|---|---|
| `user_login` | sim | Login do usuário |
| `senha` | sim | Senha em texto plano |

**Resposta (200):** dentro de `data`:

| Caso | `data` |
|---|---|
| Fluxo normal | `status: "mfa_pendente"`, `metodo` (preferencial; pode ser `null` em conta legada), `metodos_disponiveis` |
| Senha e/ou 2FA ainda não definidos | `status: "onboarding_pendente"` |

## `POST /logout`

Encerra a sessão atual. Pública.

**Resposta (200):** mensagem "Sessão encerrada."

---

# Login com Google (`oauth.py`, blueprint `oauth`)

## `GET /login`

Redireciona o navegador para a tela de autorização do Google. Pública.

## `GET /callback`

Recebe o retorno do Google, autentica o usuário já cadastrado e redireciona ao frontend. Pública.

| Parâmetro | Origem | Descrição |
|---|---|---|
| `code`, `state` | Google | Tratados pela biblioteca OAuth |

**Resposta:** redirect.

| Destino | Quando |
|---|---|
| Ponto de entrada pós-login do frontend | Sucesso; a sessão fica `mfa_pendente` ou `onboarding_pendente` (a URL não indica qual) |
| Tela de login com `?erro=usuario_nao_cadastrado` | E-mail sem usuário cadastrado |
| Tela de login com `?erro=conta_inativa` | Usuário inativo |
| Tela de login com `?erro=conta_google_invalida` | E-mail do Google não verificado, ou `sub` diferente do vinculado ao usuário |

---

# Status de sessão (`status.py`, blueprint `status`)

`/status`, `/status_completo` e `/check-session` são públicas: respondem sobre o estado, em vez de bloquear. `/me` exige sessão completa.

## `GET /status`

Estado da sessão, sem dados do usuário.

**Resposta:** `status` e campos extras conforme o estado.

| `status` | Campos extras | HTTP |
|---|---|---|
| `completa` | - | 200 |
| `onboarding_pendente` | `senha_definida` | 200 |
| `mfa_pendente` | `metodo`, `metodos_disponiveis`, `tentativas_restantes`, `reautenticar_disponivel` | 200 |
| `nao_autenticado` | - | 401 |

## `GET /status_completo`

Igual a `/status`; no estado `completa` inclui também `usuario` (uuid, funcao_clinica, is_admin, is_super_admin, status).

## `GET /me`

Dados do usuário da sessão, suas configurações e os dispositivos WebAuthn. **Sessão completa.**

**Resposta (200):** dentro de `data`: `usuario`, `configuracoes`, `webauthn` (lista de credenciais).

## `GET /check-session`

Verifica se já existe sessão ativa.

**Resposta:** 200 se existe, 401 se não.

---

# Onboarding (`onboarding.py`, blueprint `onboarding`)

Todas exigem **Onboarding**.

## `POST /definir-senha`

Define a senha inicial. Idempotente: se o usuário já tem senha, não pede outra.

| Campo (JSON) | Obrigatório | Descrição |
|---|---|---|
| `senha` | só se ainda não tiver senha | Nova senha, validada pelas regras de senha |

**Resposta (200):** `status: "escolher_2fa"`, `id_usuario`.

## `GET /2fa/status`

Informa se o usuário já tem algum método de 2FA confirmado.

**Resposta (200):** `{"tem_2fa": bool}`.

## `POST /concluir`

Conclui o onboarding. Não cadastra nada: valida que a senha e ao menos um 2FA já existem. Libera a sessão completa se o usuário comprovou um fator nesta sessão; se o fator já existia (ex.: reset de senha), deixa a sessão em MFA pendente.

**Resposta (200):**

| Caso | Conteúdo |
|---|---|
| Fator comprovado nesta sessão | `status: "onboarding_concluido"`, `id_usuario`, `id_empresa` |
| Usuário já tinha fator | `status: "mfa_pendente"`, `metodo`, `metodos_disponiveis`; o frontend segue para o 2FA |

---

# WebAuthn (`webauthn_2fa.py`, blueprint `webauthn_2fa`)

## Gerenciamento de dispositivos

### `GET /configuracoes`

Lista os dispositivos WebAuthn do usuário. **Sessão completa.**

**Resposta (200):** `{"webauthn": [...]}`.

### `POST /registrar/iniciar`

Gera o desafio de **registro** de um novo dispositivo. **Sessão completa ou onboarding.**

**Resposta (200):** opções de registro WebAuthn em JSON (`challenge` e demais campos do padrão). Dispositivos já cadastrados são excluídos.

### `POST /registrar/confirmar`

Valida a resposta de registro e salva a credencial. **Sessão completa ou onboarding.**

| Campo (JSON) | Obrigatório | Descrição |
|---|---|---|
| `credencial` | sim | Resposta do `startRegistration()` |
| `apelido` | sim | Nome do dispositivo (ex.: "Notebook do trabalho") |
| `tipo` | não | `mobile`, `usb` ou `desktop` (padrão `desktop`) |

**Resposta (201):** `{"webauthn": {"credenciais": [...]}}` com a lista atualizada.

### `DELETE /credenciais/<id_credencial>`

Remove um dispositivo do usuário logado. **Sessão completa.** A última credencial só pode ser removida se o usuário tiver TOTP confirmado.

| Parâmetro | Local | Descrição |
|---|---|---|
| `id_credencial` | caminho (inteiro) | Id da credencial a remover |

**Resposta (200):** `{"webauthn": {"credenciais": [...]}}` com a lista atualizada.

## Segundo fator no login

### `POST /2fa/iniciar`

Gera o desafio de autenticação e consome uma tentativa (limite de 3 por sessão). **MFA pendente.** Sem corpo.

**Resposta (200):** opções de autenticação WebAuthn mais `tentativas_restantes`.

### `POST /2fa/confirmar`

Valida a assinatura e promove a sessão a completa. **MFA pendente.**

| Corpo (JSON) | Descrição |
|---|---|
| Resposta de autenticação do WebAuthn | Objeto devolvido pelo navegador (usa o campo `id`) |

**Resposta (200):** `id_usuario`, `email`, `id_empresa`.

---

# TOTP (`totp_2fa.py`, blueprint `totp_2fa`)

## Cadastro e remoção

### `POST /registrar/iniciar`

Gera um secret novo (só na sessão, não no banco) e a URI para QR code. **Sessão completa ou onboarding.** Sem corpo.

**Resposta (200):** `otpauth_uri`, `secret_texto` (para digitação manual; só devolvido nesta etapa).

### `POST /registrar/confirmar`

Confirma o cadastro com o primeiro código válido e grava a credencial. **Sessão completa ou onboarding.**

| Campo (JSON) | Obrigatório | Descrição |
|---|---|---|
| `codigo` | sim | Código de 6 dígitos |

**Resposta (200):** `{"totp": {...}}`.

### `DELETE /remover`

Remove o TOTP do usuário logado. **Sessão completa.** Só é permitido se o usuário tiver pelo menos uma credencial WebAuthn. Sem corpo.

**Resposta (200):** `{"status": "removido"}`.

## Segundo fator no login

### `POST /2fa/iniciar`

Confirma que há TOTP disponível e zera o contador de tentativas do TOTP. **MFA pendente.** Sem corpo.

**Resposta (200):** `metodo: "totp"`, `tentativas_restantes`.

### `POST /2fa/confirmar`

Valida o código e promove a sessão a completa (limite de 5 tentativas por sessão). **MFA pendente.**

| Campo (JSON) | Obrigatório | Descrição |
|---|---|---|
| `codigo` | sim | Código de 6 dígitos |

**Resposta (200):** `id_usuario`, `email`, `id_empresa`.

## Segundo fator no step-up

### `POST /2fa/stepup/iniciar`

Confirma TOTP disponível para a `acao` e zera o contador do step-up. **Sessão completa.**

| Campo (JSON) | Obrigatório | Descrição |
|---|---|---|
| `acao` | sim | Ação sensível a confirmar |

**Resposta (200):** `metodo: "totp"`, `acao`, `tentativas_restantes`.

### `POST /2fa/stepup/confirmar`

Valida o código e emite o token de step-up. **Sessão completa.**

| Campo (JSON) | Obrigatório | Descrição |
|---|---|---|
| `acao` | sim | Deve ser a mesma do `/2fa/stepup/iniciar` |
| `codigo` | sim | Código de 6 dígitos |

**Resposta (200):** `token_confirmacao`, `acao`, `expira_em_segundos`.

---

# Step-up (`step_up.py`, blueprint `step_up`)

## `POST /iniciar`

Inicia a reconfirmação no método disponível para o usuário. **Sessão completa.**

| Campo (JSON) | Obrigatório | Descrição |
|---|---|---|
| `acao` | sim | Ação sensível; fica vinculada ao desafio |

**Resposta (200):**

| `metodo` | Quando | Conteúdo |
|---|---|---|
| `webauthn` | Usuário tem credencial | Opções de autenticação WebAuthn |
| `totp` | Sem WebAuthn, com TOTP | `acao`, `tentativas_restantes` |
| `senha_google` | Sem nenhum dos dois | `acao` |

## `POST /confirmar`

Valida a assinatura WebAuthn e emite o token. **Sessão completa.**

| Campo (JSON) | Obrigatório | Descrição |
|---|---|---|
| `acao` | sim | Deve ser a mesma do desafio iniciado |
| `credencial` | sim | Resposta de autenticação do WebAuthn |

**Resposta (200):** `token_confirmacao`, `acao`, `expira_em_segundos` (180).

## `POST /senha/confirmar`

Primeira etapa do fallback: confirma a senha atual e devolve a URL de reautenticação no Google. **Sessão completa.** Só é liberado para usuário sem nenhum fator ou com TOTP e tentativas esgotadas no step-up da `acao`.

| Campo (JSON) | Obrigatório | Descrição |
|---|---|---|
| `acao` | sim | Ação sensível a confirmar |
| `senha` | sim | Senha atual do usuário |

**Resposta (200):** `{"redirect_url": "..."}` para o frontend redirecionar o navegador.

## `GET /google/callback`

Segunda etapa do fallback: recebe a volta do Google e emite o token. Pública, porque o retorno pode acontecer em outra aba; a correlação é feita pelo `state`.

| Parâmetro | Origem | Descrição |
|---|---|---|
| `state` | Google | Correlaciona com a reautenticação pendente |
| `code` | Google | Código de autorização |
| `error` | Google | Presente se o usuário recusou ou o Google falhou |

**Resposta:** redirect para o ponto de entrada do frontend:

| Resultado | Querystring |
|---|---|
| Sucesso | `token_confirmacao`, `acao`, `expira_em_segundos` |
| Falha | `erro` = `reautenticacao_expirada`, `falha_google` ou `conta_google_nao_corresponde` |

## Decorator `requer_confirmacao_recente(acao)`

Não é uma rota: protege rotas sensíveis de outros domínios. Exige o token no header `X-Stepup-Token`, apaga-o ao aceitar e responde `403` com `{"erro": "confirmacao_requerida", "acao": ...}` quando ausente, incorreto ou expirado. A função `token_recente_valido(acao)` faz a mesma checagem de forma condicional dentro de uma view.

---

# Resumo das rotas

| Blueprint | Método | Rota | Sessão exigida |
|---|---|---|---|
| auth | POST | `/login` | Pública |
| auth | POST | `/logout` | Pública |
| oauth | GET | `/login` | Pública |
| oauth | GET | `/callback` | Pública |
| status | GET | `/status` | Pública |
| status | GET | `/status_completo` | Pública |
| status | GET | `/me` | Sessão completa |
| status | GET | `/check-session` | Pública |
| onboarding | POST | `/definir-senha` | Onboarding |
| onboarding | GET | `/2fa/status` | Onboarding |
| onboarding | POST | `/concluir` | Onboarding |
| webauthn_2fa | GET | `/configuracoes` | Sessão completa |
| webauthn_2fa | POST | `/registrar/iniciar` | Completa ou onboarding |
| webauthn_2fa | POST | `/registrar/confirmar` | Completa ou onboarding |
| webauthn_2fa | DELETE | `/credenciais/<id_credencial>` | Sessão completa |
| webauthn_2fa | POST | `/2fa/iniciar` | MFA pendente |
| webauthn_2fa | POST | `/2fa/confirmar` | MFA pendente |
| totp_2fa | POST | `/registrar/iniciar` | Completa ou onboarding |
| totp_2fa | POST | `/registrar/confirmar` | Completa ou onboarding |
| totp_2fa | DELETE | `/remover` | Sessão completa |
| totp_2fa | POST | `/2fa/iniciar` | MFA pendente |
| totp_2fa | POST | `/2fa/confirmar` | MFA pendente |
| totp_2fa | POST | `/2fa/stepup/iniciar` | Sessão completa |
| totp_2fa | POST | `/2fa/stepup/confirmar` | Sessão completa |
| step_up | POST | `/iniciar` | Sessão completa |
| step_up | POST | `/confirmar` | Sessão completa |
| step_up | POST | `/senha/confirmar` | Sessão completa |
| step_up | GET | `/google/callback` | Pública |