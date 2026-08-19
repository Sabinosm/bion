# Fluxo de Autenticação

Documentação do sistema de autenticação multifatorada, cobrindo login por senha, login social (Google), segundo fator via WebAuthn, onboarding de novos usuários, step-up authentication e status de sessão.

---

# Contexto e conceitos

## Visão geral

A autenticação garante duas coisas: que quem está logado é quem diz ser, e que privilégios corretos são concedidos/negados. O sistema combina dois caminhos de entrada com níveis de confiança diferentes:

1. **Usuário e senha** — `user_login` + `senha` via JSON. Validado no front e no back. Se o usuário tiver WebAuthn cadastrado, precisa confirmá-lo antes de ganhar acesso (segundo fator). Se não tiver, a sessão é liberada direto após a senha.

2. **OAuth (Google)** — login usando o e-mail já cadastrado por um admin. O Google aqui só prova posse do e-mail; **nunca cria conta nova**. Autenticar com sucesso via Google já é considerado prova de identidade suficiente: a sessão é liberada como completa direto, mesmo que o usuário tenha WebAuthn cadastrado — o login via Google nunca exige o segundo fator. O único bloqueio possível é o onboarding pendente, se o usuário ainda não tiver senha definida.

Em ambos os casos, ao final, o sistema gera uma **sessão via cookie httpOnly**, com duração de 8 horas, que garante identidade, empresa associada e configurações do usuário.

## Sessão: estados e progressão

A sessão nunca pula direto para "completa". Ela passa por estados intermediários, guardados como flags dentro do próprio cookie de sessão:

| Estado | Flag na sessão | Significa |
|---|---|---|
| Onboarding pendente | `onboarding_pendente=True` | Primeiro acesso; falta definir senha |
| MFA pendente | `mfa_pendente=True` | Login por senha ok, usuário tem WebAuthn cadastrado e falta confirmar o 2º fator |
| Completa | nenhuma das flags acima + `id_empresa` definido | Usuário tem acesso pleno |

`id_empresa` só é gravado na sessão no momento em que ela vira completa — é o sinal de que a autenticação terminou. Enquanto pendente (onboarding ou MFA), o usuário está "meio-logado": tem `id_usuario` na sessão, mas nenhuma rota que dependa de `id_empresa` deve confiar nele ainda.

Onboarding e MFA são mutuamente exclusivos: um usuário com `onboarding_pendente=True` ainda não tem WebAuthn cadastrado (é primeiro acesso, e o cadastro de WebAuthn não faz mais parte do onboarding — ver seção própria), então nunca chega a `mfa_pendente` antes de concluir o onboarding.

## WebAuthn: o mecanismo por trás de tudo

WebAuthn é o padrão (W3C/FIDO Alliance) que autentica sem senha, trocando segredo compartilhado por criptografia assimétrica. A ideia central:

- **Registro**: o dispositivo gera um par de chaves. A privada fica presa no hardware (Secure Enclave, TPM, chip de segurança); a pública vai pro servidor.
- **Autenticação**: o servidor manda um `challenge` aleatório. O usuário confirma presença (biometria/PIN). O dispositivo assina o challenge com a chave privada. O servidor valida com a chave pública salva.
Como a chave é vinculada ao domínio (origin-bound), o mecanismo é nativamente resistente a phishing — não existe "senha" pra vazar ou reutilizar em outro site.

Dispositivos suportados vão de autenticadores de plataforma (Face ID, Windows Hello, Touch ID) a autenticadores de itinerância (YubiKey, chaves FIDO2 via USB/NFC/Bluetooth) e celulares como chave remota via passkey.

**Importante**: esse mesmo mecanismo criptográfico é reaproveitado em **dois contextos diferentes** no sistema, cada um com sua própria chave de sessão para o challenge (para não haver colisão entre fluxos):

| Contexto | Onde | Chave de sessão do challenge | `user_verification` | Papel do WebAuthn |
|---|---|---|---|---|
| Segundo fator (login por senha) | `webauthn_2fa.py` | `mfa_webauthn_challenge` | `REQUIRED` | Confirmação de sessão pendente |
| Reconfirmação de identidade (ação sensível) | `step_up.py` | `stepup_challenge` (+ `acao` vinculada) | `REQUIRED` | Reautenticação pontual, sessão já completa — método preferencial, quando o usuário tem credencial cadastrada |

`REQUIRED` obriga o autenticador a confirmar identidade localmente (PIN ou biometria) antes de assinar — não basta só presença física (ex.: tocar num sensor sem ele de fato ler nada). Sem isso, alguém com o dispositivo desbloqueado mas sem saber o PIN/senha do sistema operacional ainda passaria pelo desafio em certos autenticadores.

O cadastro da credencial (registro) não faz mais parte do onboarding — passou a ser uma funcionalidade das configurações da conta, com o usuário já em sessão completa, usando as mesmas funções de registro do `py_webauthn` (`generate_registration_options` / `verify_registration_response`) que antes viviam em `onboarding.py`.

## Configuração centralizada (RP ID, origin, frontend)

Valores que antes estavam hardcoded (`"127.0.0.1"` repetido pelos módulos que usam WebAuthn; path de redirect fixo em `oauth.py`) foram centralizados em módulos de configuração próprios, lidos de variáveis de ambiente:

| Módulo | Variáveis | Usado por |
|---|---|---|
| `webauthn_config.py` | `WEBAUTHN_RP_ID`, `WEBAUTHN_RP_NAME`, `WEBAUTHN_ORIGIN` | `webauthn_2fa.py`, `step_up.py`, e o cadastro de credencial nas configurações |
| `frontend_config.py` | `FRONTEND_URL` | `oauth.py`, `step_up.py` (redirect de volta do fallback de reautenticação) |

`WEBAUTHN_ORIGIN` precisa ser uma URL completa com esquema (ex.: `https://app.bion.com.br`), não um host puro — é assim que o navegador preenche `clientDataJSON.origin`, e é contra esse valor exato que a verificação da assinatura compara. Um host sem esquema funciona por acidente em alguns cenários de desenvolvimento e falha sempre em produção com HTTPS real.

`FRONTEND_URL` existe porque o backend (Flask) e o frontend (arquivos estáticos servidos por outro processo, ex. Vite/live-server) rodam em origens diferentes — um `redirect()` do Flask com path relativo (ex. `/paginas/algo.html`) é resolvido pelo navegador contra a origem do Flask, não a do frontend, e por isso precisa da URL completa da outra origem.

Em desenvolvimento, os defaults caem em `127.0.0.1` / `http://127.0.0.1:5000` (WebAuthn) e `http://localhost:5500` (frontend) — nunca devem ser usados em produção sem sobrescrever via variável de ambiente.

## Limite de tentativas do 2FA e volta ao login

Cada chamada a `POST /2fa/iniciar` consome uma tentativa, contada em `mfa_tentativas` na sessão (zera a cada novo login por senha). Ao atingir o **limite de 3 tentativas por sessão** (`MAX_TENTATIVAS_MFA`), a rota passa a responder `429 limite_tentativas_excedido` em vez de gerar novo desafio.

Não existe mais, dentro da própria sessão de 2FA, um caminho para pular o desafio — nem por falta de autenticador disponível, nem por esgotamento de tentativas. Quando isso acontece, o frontend orienta o usuário a voltar à tela de login e reautenticar por um dos dois caminhos normais:

- **Por senha**: reinicia o contador de tentativas (`mfa_tentativas` é gravado do zero a cada `POST /login`), permitindo um novo ciclo de até 3 tentativas de WebAuthn.
- **Por Google**: como login via Google nunca exige 2FA (ver "Visão geral"), essa reautenticação já basta para liberar a sessão completa, sem passar por `mfa_pendente`.

Essa é uma simplificação deliberada em relação a um mecanismo anterior de fallback automático (que promovia a sessão a completa a partir de dentro do próprio fluxo de MFA, via um marcador de sessão validado no callback do Google). Como login via Google deixou de exigir 2FA em qualquer circunstância, esse fallback ficou redundante — o mesmo resultado agora é alcançado simplesmente reautenticando pelo caminho normal do Google.

## Onboarding: primeiro acesso

Onboarding (enrollment) é o processo de cadastrar, verificar identidade e configurar acesso de um novo usuário antes de conceder qualquer entrada — é a primeira linha de defesa em IAM (Identity and Access Management).

Disparado quando `usuario.onboarding_pendente == True`, tanto após o primeiro login via Google quanto via senha. Passo único:

1. Definir senha (idempotente — se já existir, só conclui o onboarding sem pedir senha nova)
2. Sessão promovida a completa

O cadastro de WebAuthn não faz mais parte deste fluxo. Reduzir o onboarding a um único passo diminui o atrito do primeiro acesso: a sessão é liberada assim que a senha é definida, sem exigir hardware de autenticação na hora. Quem quiser usar WebAuthn como segundo fator em logins futuros por senha pode cadastrá-lo quando quiser, depois, nas configurações da conta — a partir daí, o próximo login por senha (mas não por Google) passará a exigir esse segundo fator.

## Login: senha vs. Google

No login por senha, se o usuário só tiver conta via Google (sem `hash_senha`), a rota rejeita com instrução para logar pelo Google. Depois de senha validada, o fluxo verifica 2FA:

- Sem WebAuthn cadastrado → sessão completa direto (empresa liberada)
- Com WebAuthn cadastrado → sessão fica `mfa_pendente`, aguardando confirmação em `webauthn_2fa.py`

No login via Google (`oauth.py`), o usuário **precisa já existir** (cadastrado por admin) e estar com `status == "ativo"`. O Google só confirma o e-mail. Na primeira vez, vincula `google_sub` ao usuário. Depois, decide entre onboarding pendente (se faltar senha) ou sessão completa direto — login via Google nunca resulta em `mfa_pendente`, independentemente de o usuário ter WebAuthn cadastrado ou não.

## Step-up authentication: reconfirmar mesmo já logado

Mesmo com sessão completa, certas ações sensíveis (excluir prontuário, alterar prescrição, conceder acesso admin) exigem reconfirmação de identidade antes de prosseguir — é uma segunda camada, independente do MFA do login.

Existem dois métodos, conforme o que o usuário tem cadastrado:

**1. WebAuthn (preferencial)**, para quem já tem credencial cadastrada:

1. Rota sensível responde `403 confirmacao_requerida` se não houver token válido.
2. Frontend chama `/stepup/iniciar` informando qual `acao` quer confirmar. O servidor identifica que o usuário tem WebAuthn e devolve `metodo: "webauthn"` com o desafio. Essa ação fica **vinculada ao challenge** na sessão — não dá pra iniciar desafio pra uma ação e confirmar outra.
3. Frontend chama `/stepup/confirmar` com a assinatura WebAuthn. Se a `acao` bater com a vinculada ao challenge, emite um **token de uso único**, de vida curta (180s), salvo em `stepup_token`.

**2. Senha + reautenticação Google (fallback)**, para quem não tem WebAuthn cadastrado:

1. `/stepup/iniciar` detecta a ausência de credencial e devolve `metodo: "senha_google"` em vez do desafio.
2. Frontend pede a senha atual e chama `/stepup/senha/confirmar`. Validada a senha, o servidor cria um registro `StepUpReautenticacao` (usuário + ação + `state` de correlação, expira em 300s) e devolve a URL de autorização do Google.
3. Frontend redireciona o navegador para essa URL. O parâmetro `prompt=login` é exigido explicitamente — sem ele, se o usuário já tiver uma sessão Google ativa no navegador, o Google devolveria acesso via SSO silencioso, sem pedir nada de novo, o que não reconfirmaria identidade alguma.
4. O Google volta em `/stepup/google/callback` — uma rota própria, separada do callback de login (`oauth.google_callback`), para não interferir em `onboarding_pendente`/`mfa_pendente` do fluxo de login. O servidor confere o `state` contra o `StepUpReautenticacao` pendente e que o e-mail devolvido pelo Google é o mesmo do usuário que confirmou a senha na etapa anterior. Se tudo bater, emite o mesmo tipo de token (`stepup_token`) que o caminho WebAuthn geraria, e redireciona de volta ao frontend com o token na querystring.

Em ambos os casos, o resultado final é idêntico: um `StepUpToken` de 180s vinculado a (usuário, ação). A rota sensível, decorada com `@requer_confirmacao_recente("acao")`, exige esse token no header `X-Stepup-Token` e não distingue qual dos dois métodos o gerou. O token é apagado assim que lido — mesmo que a ação decorada falhe depois por outro motivo.

**Por que o fallback é mais fraco, e por que existe mesmo assim**

Senha + Google prova posse de duas credenciais que já autenticaram a sessão original (não é um fator independente do que já foi usado para logar), enquanto WebAuthn prova posse de um hardware específico — propriedade mais forte para uma reconfirmação. A persistência do estado intermediário em `StepUpReautenticacao` (banco), em vez da sessão Flask, existe porque o fluxo atravessa um redirect real de navegador e pode voltar em uma aba diferente da que iniciou; usar a sessão, como o antigo fallback de MFA fazia, não seria confiável nesse caso.

É uma redução real de garantia, aceita deliberadamente: sem esse caminho, qualquer usuário sem WebAuthn cadastrado ficaria irrecuperavelmente incapaz de confirmar qualquer ação sensível, sem alternativa nenhuma até cadastrar um dispositivo nas configurações.

## Status de sessão

`status.py` existe porque nem toda checagem de sessão deve **bloquear** — às vezes só se quer **perguntar** em que estado a sessão está, pra decidir pra onde navegar. Usada logo após o redirect do Google, para decidir entre onboarding, confirmação de 2FA ou dashboard.

Diferente de `/auth/me`, `/status` não usa `@requer_login`: ela responde com o estado mesmo que a sessão esteja incompleta, e só devolve 401 se não houver sessão nenhuma iniciada.

Quando `mfa_pendente`, a resposta inclui `tentativas_restantes` e `reautenticar_disponivel`, permitindo ao frontend decidir entre oferecer "tentar de novo" ou já orientar o usuário a voltar para a tela de login.

---