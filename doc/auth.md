# Fluxo de Autenticação

Documentação do sistema de autenticação do Bion, cobrindo login por senha, login social (Google), segundo fator (WebAuthn e TOTP), onboarding de novos usuários, step-up authentication e status de sessão.

---

# Contexto e conceitos

## Visão geral

A autenticação garante duas coisas: que quem está logado é quem diz ser e que a sessão só ganha acesso pleno depois de provar isso. O sistema tem dois caminhos de entrada, que convergem para o mesmo segundo fator:

1. **Usuário e senha**: `user_login` + `senha`. A senha é validada com Argon2id (o hash é regravado automaticamente se os parâmetros do algoritmo evoluírem). Usuário inexistente, inativo ou sem senha (só Google) recebe a mesma resposta de credencial inválida, para não revelar quais contas existem.
2. **Google (OAuth)**: login pelo e-mail já cadastrado por um admin. O Google só prova a posse do e-mail e **nunca cria conta**. Na primeira vez, o `google_sub` é vinculado ao usuário; nas seguintes, o `sub` devolvido precisa ser o mesmo, e o e-mail precisa estar verificado pelo Google.

Nos dois casos o 2FA é obrigatório: **WebAuthn ou TOTP**, sem caminho de login que dispense o segundo fator. A única etapa que vem antes dele é o onboarding, quando o usuário ainda não tem senha e fator definidos.

A sessão é um **cookie httpOnly** (`session.permanent = True`) e guarda identidade, privilégios e flags de estado.

## Camadas e arquivos

| Arquivo | Responsabilidade |
|---|---|
| `login.py` | Login por senha e logout |
| `oauth.py` | Login via Google (callback, vínculo do `google_sub`) |
| `onboarding.py` | Primeiro acesso: definir senha, checar 2FA, concluir; regra que fecha o onboarding |
| `webauthn_2fa.py` | Cadastro/remoção de dispositivos WebAuthn e confirmação do login |
| `totp_2fa.py` | Cadastro/remoção de TOTP, confirmação do login e do step-up |
| `step_up.py` | Reconfirmação de identidade antes de ações sensíveis |
| `mfa.py` | Decisão de qual método de 2FA oferecer |
| `services.py` | Validação de senha e promoção da sessão a completa |
| `status.py` | Estado da sessão, dados do usuário e verificação de sessão ativa |
| `webauthn_config.py` / `frontend_config.py` | Configuração por variáveis de ambiente |

## Sessão: estados e progressão

A sessão não vai direto para "completa". Passa por estados intermediários, guardados como flags no próprio cookie:

| Estado | Como se reconhece | Significa |
|---|---|---|
| Onboarding pendente | `onboarding_pendente=True` | Falta definir senha e/ou cadastrar um método de 2FA |
| MFA pendente | `mfa_pendente=True` | Primeiro fator ok; falta confirmar o segundo |
| Completa | nenhuma das flags + `id_empresa` definido | Acesso pleno |

`id_empresa` só é gravado quando a sessão vira completa: ao confirmar o 2FA (`liberar_sessao_completa`) ou ao concluir o onboarding. Enquanto pendente, o usuário está "meio-logado": tem `id_usuario` na sessão, mas nenhuma rota que dependa de `id_empresa` deve confiar nele.

O `mfa_pendente` expira 5 minutos depois de criado, prazo fixo que nenhuma atividade renova, e não só pela inatividade do cookie (ver `sessao_fluxo.md`).

### Chaves gravadas na sessão

| Chave | Gravada por | Para quê |
|---|---|---|
| `id_usuario`, `uuid_usuario` | login e callback do Google | Identidade da sessão |
| `is_admin`, `funcao_clinica`, `is_super_admin` | login, callback do Google e conclusão do onboarding | Privilégios; `is_admin` e `funcao_clinica` são independentes (admin que também atende). São revalidados a partir do banco nas rotas que pedem (ver `sessao_fluxo.md`) |
| `senha_versao` | login e callback do Google | Snapshot da versão da senha, para invalidar sessões quando a senha muda depois |
| `onboarding_pendente` | login e callback do Google | Flag de onboarding |
| `onboarding_fator_comprovado` | cadastro de fator durante o onboarding | Indica que o usuário comprovou a posse de um fator nesta sessão |
| `mfa_pendente` | início do MFA pendente | Flag de segundo fator pendente |
| `mfa_tentativas` | `/webauthn/2fa/iniciar` | Tentativas de desafio WebAuthn no login |
| `totp_tentativas` | `/totp/2fa/iniciar` e confirmação | Tentativas de TOTP no login |
| `mfa_webauthn_challenge` | `/webauthn/2fa/iniciar` | Desafio do login |
| `registro_webauthn_challenge` | `/webauthn/registrar/iniciar` | Desafio de cadastro de dispositivo |
| `totp_secret_pendente` | `/totp/registrar/iniciar` | Secret ainda não confirmado |
| `stepup_challenge` | `/stepup/iniciar` | Desafio do step-up + ação vinculada |
| `stepup_totp_tentativas`, `stepup_totp_acao` | início do step-up TOTP | Tentativas e ação vinculada |
| `id_empresa` | liberação da sessão completa | Sinal de que a autenticação terminou; sem ele, os decorators encerram a sessão |
| `uuid_empresa` | primeira consulta ao UUID da empresa | UUID da empresa, guardado para não consultar de novo |

Ao liberar a sessão completa, `mfa_pendente`, `mfa_webauthn_challenge`, `mfa_tentativas` e `totp_tentativas` são descartados.

## Métodos de 2FA

Dois métodos, sempre nesta ordem de preferência: **WebAuthn**, depois **TOTP**. `mfa.py` expõe a decisão:

| Função | Devolve | Uso |
|---|---|---|
| `metodo_2fa_preferencial` | `"webauthn"` se houver 1+ credencial; senão `"totp"` se houver TOTP confirmado; senão `None` | Método oferecido primeiro no login |
| `metodos_2fa_disponiveis` | Lista com todos os métodos utilizáveis | Tela de escolha do frontend (`/status`) |
| `metodo_stepup` | O mesmo que a preferencial, ou `"senha_google"` se o usuário não tiver nenhum | Método do step-up |
| `usuario_tem_algum_2fa` | `True` se tem WebAuthn ou TOTP confirmado | Checagem de onboarding |

`None` só deveria ocorrer em conta legada sem nenhum fator migrado. Nunca significa "libera direto".

### WebAuthn

Padrão (W3C/FIDO) que troca segredo compartilhado por criptografia assimétrica. No cadastro, o dispositivo gera um par de chaves: a privada fica no hardware e a pública vai para o servidor. Na autenticação, o servidor envia um `challenge` aleatório, o usuário confirma presença local (PIN ou biometria) e o dispositivo assina o desafio; o servidor valida com a chave pública. Como a chave é vinculada ao domínio, o mecanismo resiste a phishing.

O mesmo mecanismo é usado em três contextos, cada um com sua chave de sessão para o desafio, para os fluxos não colidirem:

| Contexto | Rotas | Chave do desafio | Papel |
|---|---|---|---|
| Confirmação do login | `/webauthn/2fa/*` | `mfa_webauthn_challenge` | Promove a sessão pendente a completa |
| Cadastro de dispositivo | `/webauthn/registrar/*` | `registro_webauthn_challenge` | Registra uma credencial nova |
| Step-up | `/stepup/iniciar` e `/stepup/confirmar` | `stepup_challenge` (+ ação) | Reautenticação pontual, sessão já completa |

Em todos, `user_verification` é `REQUIRED`: o autenticador confirma a identidade localmente, e só presença física não basta. A cada autenticação bem-sucedida o `sign_count` da credencial é atualizado. Cada credencial tem apelido e tipo (`mobile`, `usb` ou `desktop`), e o cadastro usa `exclude_credentials` para não registrar o mesmo autenticador duas vezes.

### TOTP

Código de 6 dígitos de um app autenticador, aceito com tolerância de uma janela de 30 segundos para cada lado. O cadastro tem duas etapas:

1. `/totp/registrar/iniciar` gera um secret novo e devolve a URI `otpauth://` (para QR code) e o `secret_texto` (digitação manual). O secret **não vai ao banco**: fica só na sessão (`totp_secret_pendente`).
2. `/totp/registrar/confirmar` exige o primeiro código válido. Só então a credencial é criada ou substituída e `confirmado` vira `True`, junto com a troca do secret. Um TOTP já em uso continua válido até lá, mesmo que o cadastro seja reiniciado.

Depois de confirmado, o secret nunca mais é exposto por nenhuma rota.

### Regras de remoção

| Remover | Permitido quando |
|---|---|
| Credencial WebAuthn | Não é a última, ou o usuário tem TOTP confirmado |
| TOTP | O usuário tem pelo menos uma credencial WebAuthn |

Em ambos os casos, o usuário nunca fica sem 2FA.

## Configuração centralizada

| Módulo | Variáveis | Padrão | Usado por |
|---|---|---|---|
| `webauthn_config.py` | `WEBAUTHN_RP_ID` | `bion-one.vercel.app` | Todos os módulos WebAuthn |
| | `WEBAUTHN_RP_NAME` | `Bion` | Tela de biometria e emissor do TOTP |
| | `WEBAUTHN_ORIGIN` | `https://bion-one.vercel.app` | Verificação das assinaturas |
| `frontend_config.py` | `FRONTEND_URL` | `https://bion-one.vercel.app` | Redirects do Google e do step-up |

`WEBAUTHN_ORIGIN` precisa ser uma URL completa com esquema, porque é assim que o navegador preenche `clientDataJSON.origin`, e a verificação compara contra esse valor exato. `WEBAUTHN_RP_ID` não leva esquema nem porta.

`FRONTEND_URL` existe porque backend e frontend rodam em origens diferentes: um `redirect()` com path relativo seria resolvido contra a origem do Flask. Por isso todo redirect para o frontend monta a URL completa, e o backend só conhece pontos de entrada fixos (`oauth_callback.html`, `login.html`, `stepup_callback.html`).

## Limites de tentativas

| Fluxo | Limite | Contador (sessão) | Quando zera | Ao esgotar |
|---|---|---|---|---|
| WebAuthn no login | 3 | `mfa_tentativas` | Novo login | `429 limite_tentativas_excedido`; o frontend tenta TOTP |
| TOTP no login | 5 | `totp_tentativas` | Novo login ou `/totp/2fa/iniciar` | `429 limite_tentativas_excedido`; sem outro caminho |
| TOTP no step-up | 5 | `stepup_totp_tentativas` | A cada início do step-up TOTP | `429`; libera o fallback senha + Google |

No WebAuthn, **cada pedido de desafio** conta como uma tentativa, não importa por que a anterior falhou (sem autenticador, PIN errado, timeout, cancelamento); o contador só avança depois de as opções serem geradas com sucesso. No TOTP, cada código errado conta, porque são só 6 dígitos e uma falha pode ser tentativa de adivinhação.

Esgotar os dois métodos no login é bloqueio: o frontend orienta contato com o administrador. Como todos os contadores vivem na sessão, um novo login (por senha ou por Google) recomeça o ciclo.

---

# Fluxos

## Login por senha

1. O frontend envia `user_login` e `senha` para `/login`.
2. `AuthService.autenticar` valida as credenciais.
3. A sessão é **reiniciada** e recebe identidade, privilégios e `senha_versao`.
4. O sistema reavalia o onboarding (ver abaixo). Se continuar pendente, grava `onboarding_pendente` e responde `status: onboarding_pendente`.
5. Caso contrário, inicia o MFA pendente e responde `status: mfa_pendente`, com `metodo` (preferencial) e `metodos_disponiveis`.
6. O frontend executa o segundo fator (próxima seção).

## Login via Google

1. O frontend abre `/login` do blueprint OAuth, que redireciona ao Google (a URI de retorno vem de `GOOGLE_REDIRECT_URI` ou da rota de callback).
2. O Google volta em `/callback`. O sistema busca o usuário pelo e-mail devolvido.
3. Usuário não cadastrado ou inativo: redirect para a tela de login com `?erro=usuario_nao_cadastrado` ou `?erro=conta_inativa`.
4. E-mail não verificado, ou `sub` diferente do já vinculado ao usuário: redirect com `?erro=conta_google_invalida`.
5. Na primeira vez, vincula o `google_sub`.
6. Reinicia a sessão (mesmos campos do login por senha) e reavalia o onboarding: pendente grava `onboarding_pendente`; senão, inicia o MFA pendente.
7. Redireciona para o ponto de entrada do frontend. A URL **não** diz em que estado a sessão ficou: o frontend consulta `/status` e decide para onde ir.

## Onboarding: primeiro acesso

Disparado quando `onboarding_pendente` está ativo, após login por senha ou por Google. Dois passos, e a conclusão exige **os dois requisitos presentes**:

1. **Definir senha** (`/definir-senha`): idempotente. Quem já tem senha (ex.: cadastrado por admin) não digita outra; o usuário passa a `ativo` ao definir uma senha nova.
2. **Cadastrar e confirmar ao menos um método de 2FA**, WebAuthn ou TOTP (não os dois), pelas mesmas rotas de cadastro das configurações da conta. `/2fa/status` informa se já há algum.
3. **Concluir** (`/concluir`): valida senha e 2FA e desliga `onboarding_pendente`. Se o usuário comprovou um fator **nesta sessão** (cadastrou e confirmou com assinatura ou código válidos), a sessão é liberada com `id_empresa`. Se o fator já existia antes (ex.: reset de senha por admin), a sessão fica `mfa_pendente` e só vira completa depois de confirmar o 2FA, como em qualquer login.

### Usuário desativado durante o onboarding

Em `/definir-senha` e `/concluir`, se o usuário foi desativado (ou removido) desde o login, a sessão é encerrada e nada é gravado ou liberado. Assim, definir a senha não reativa quem um admin acabou de desativar, e concluir o onboarding não libera a sessão dele.

### Cadastro de fator durante o onboarding

No onboarding, o cadastro de WebAuthn e TOTP só é permitido a quem ainda não tem nenhum fator confirmado ou já cadastrou um nesta própria sessão. Quem já tinha fator (ex.: após reset de senha) não troca nem acrescenta fatores antes de confirmar o 2FA; isso é feito depois, nas configurações da conta.

### Regra que fecha o onboarding no login

No login (por senha ou Google), se `onboarding_pendente` estiver ativo mas o usuário **já tem senha e 2FA confirmado**, a flag é desligada e o fluxo segue normal para o 2FA. Exige os dois requisitos, e não apenas um.

### Reset de senha por admin

Não cria estado separado: zera `hash_senha` e marca `onboarding_pendente=True`. Os fatores de 2FA já confirmados não são apagados. No acesso seguinte o usuário cai no onboarding para definir a senha nova, e como já tem 2FA, o passo de cadastro de fator não é pedido de novo. Ao concluir, a sessão passa pela confirmação do 2FA antes de ficar completa.

## Segundo fator no login

Com a sessão em `mfa_pendente`, o frontend orquestra a ordem. O servidor aceita qualquer um dos dois métodos que o usuário tenha:

**WebAuthn**

1. `/webauthn/2fa/iniciar`: consome uma tentativa, gera o desafio (guardado em `mfa_webauthn_challenge`) e devolve as opções com `tentativas_restantes`.
2. `/webauthn/2fa/confirmar`: valida a assinatura contra a credencial do usuário, atualiza o `sign_count` e libera a sessão.

**TOTP**

1. `/totp/2fa/iniciar`: confirma que há TOTP e zera `totp_tentativas`. Não gera desafio.
2. `/totp/2fa/confirmar`: valida o código; se errado, soma uma tentativa e devolve `tentativas_restantes`; se certo, libera a sessão.

Nos dois casos, a liberação é a mesma: `AuthService.liberar_sessao_completa` marca o usuário como `ativo`, descarta os estados temporários do 2FA e grava `id_empresa`. A resposta traz `id_usuario`, `email` e `id_empresa`. Se o usuário foi desativado enquanto o 2FA estava pendente, nada é liberado: o status não é alterado e a sessão é encerrada.

## Step-up authentication: reconfirmar mesmo já logado

Certas ações sensíveis (excluir prontuário, alterar prescrição, conceder acesso admin) exigem reconfirmação de identidade antes de prosseguir, uma camada independente do MFA do login. O resultado de qualquer método é um **token de uso único**, de 180 segundos, vinculado a (usuário, ação).

### Uso pelo lado da rota

- `@requer_confirmacao_recente("acao")` exige o token no header `X-Stepup-Token` e responde `403 confirmacao_requerida` quando ele está ausente, incorreto ou expirado. O token aceito é apagado na hora, mesmo que a ação falhe depois.
- `token_recente_valido("acao")` faz a mesma checagem de forma condicional dentro de uma view, para rotas que só são sensíveis conforme o payload (ex.: atualização de usuário que mexe em `is_admin`).
- Para escrita e exclusão auditadas, o decorator `@acao_sensivel` aplica o step-up e grava o log na mesma transação (ver `auditoria_fluxo.md`).

### Ordem dos métodos

O frontend chama `/stepup/iniciar` com a `acao`, e o servidor responde conforme o que o usuário tem:

| Método | Quando | Como funciona |
|---|---|---|
| `webauthn` | Tem credencial cadastrada | Devolve o desafio, vinculado à `acao` em `stepup_challenge`; `/stepup/confirmar` valida a assinatura e emite o token |
| `totp` | Sem WebAuthn, mas com TOTP confirmado | Já devolve `tentativas_restantes` (o reset é feito ali); `/totp/2fa/stepup/confirmar` valida o código e emite o token |
| `senha_google` | Sem nenhum dos dois | Fallback em duas etapas (abaixo) |

A `acao` fica **vinculada** ao desafio: não é possível iniciar um step-up para uma ação e confirmar outra. Para quem tem WebAuthn e quer usar TOTP (ex.: depois de uma falha do WebAuthn), `/totp/2fa/stepup/iniciar` reinicia o contador do TOTP.

### Quando o fallback está liberado

O servidor confere em `/stepup/senha/confirmar`, e não basta o frontend pedir:

| Situação do usuário | Fallback |
|---|---|
| Sem nenhum fator | Liberado |
| Tem TOTP e esgotou as tentativas do step-up da ação | Liberado |
| Tem TOTP e ainda tem tentativas | Não |
| Só tem WebAuthn | Não (o WebAuthn não tem contador de tentativas) |

### Fallback: senha + Google

1. `/stepup/senha/confirmar` valida a senha atual, cria um registro `StepUpReautenticacao` (usuário, ação, `state` e `nonce`, expira em 300 segundos) e devolve a URL de autorização do Google.
2. O frontend redireciona o navegador. A URL usa `prompt=login`: sem ele, uma sessão Google ativa devolveria acesso por SSO silencioso, sem reconfirmar identidade alguma.
3. O Google volta em `/stepup/google/callback`, rota própria e separada do callback de login, para não interferir em `onboarding_pendente` e `mfa_pendente`. O servidor confere o `state`, a senha confirmada, a validade e o `nonce` do id_token, e exige que o e-mail do Google seja o do usuário que confirmou a senha, esteja verificado e, se o usuário já tiver `google_sub` vinculado, que o `sub` seja o mesmo.
4. Se tudo bater, emite o mesmo token dos outros métodos e redireciona ao frontend com `token_confirmacao`, `acao` e `expira_em_segundos` na querystring; em qualquer falha, redireciona com `?erro=` (`reautenticacao_expirada`, `falha_google` ou `conta_google_nao_corresponde`) e descarta a pendência.

O estado intermediário fica em banco, e não na sessão Flask, porque o fluxo atravessa um redirect real e pode voltar em uma aba diferente da que iniciou.

### Por que o step-up tem fallback

No login, perder os dois fatores é bloqueio total. No step-up a pessoa já está dentro do sistema, e negar toda forma de confirmar uma ação seria rígido demais para quem não tem fator ou esgotou o TOTP; por isso o fallback senha + Google existe nesses casos. Ele é deliberadamente mais fraco que WebAuthn e TOTP: prova a posse de duas credenciais que já autenticaram a sessão original, e não de algo além dela.

## Status de sessão

`status.py` existe porque nem toda checagem de sessão deve **bloquear**: às vezes só se quer **perguntar** em que estado ela está, para decidir para onde navegar, por exemplo logo após o redirect do Google.

| Situação | `/status` responde |
|---|---|
| Sem sessão, ou MFA pendente expirado (a sessão é limpa) | `401 nao_autenticado` |
| Onboarding pendente | `200 onboarding_pendente` + `senha_definida` |
| MFA pendente | `200 mfa_pendente` + `metodo`, `metodos_disponiveis`, `tentativas_restantes`, `reautenticar_disponivel` |
| Completa | `200 completa` |

`reautenticar_disponivel` fica `true` quando as tentativas de WebAuthn se esgotam, para o frontend decidir entre oferecer "tentar de novo" e orientar o usuário a reautenticar. `/status_completo` acrescenta o `usuario` no estado `completa`, e é o que o `watchSession.js` usa para reconciliar o perfil e detectar troca de identidade.

`/me` exige sessão completa: sessões em onboarding ou com 2FA pendente não recebem dados do usuário.