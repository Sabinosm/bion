# Sessão e Controle de Acesso

Documentação do pacote de sessão do Bion (`src/core/session`): como o estado da sessão é lido, quais decorators protegem as rotas e o que cada um exige. Os fluxos que criam e promovem a sessão (login, Google, onboarding, 2FA) estão em `auth_fluxo.md`.

---

# Contexto e conceitos

## Visão geral

A sessão é um **cookie httpOnly** que guarda quem está logado e em que estado de autenticação ele está. O pacote de sessão responde a duas perguntas para cada rota:

1. A sessão está **liberada**? (há usuário, o onboarding terminou e o segundo fator foi confirmado)
2. O usuário tem o **papel** que a rota exige? (administrador, médico, enfermeiro, super admin)

Cada decorator já faz a checagem completa de sessão e, em seguida, a de papel. Por isso **nenhum precisa ser empilhado com o decorator de login**: empilhar não quebra nada, só é redundante.

## Módulos

| Arquivo | Responsabilidade | Depende de |
|---|---|---|
| `sessaoUsuarios.py` | Getters dos dados da sessão e helpers compartilhados (respostas 401/403, preenchimento do `g`) | Nenhum outro módulo de sessão |
| `sessaoAutenticacao.py` | Checagem base de sessão, fábrica de decorators e `requer_login` | `sessaoUsuarios`, `sessaoPrivilegios` |
| `sessaoPrivilegios.py` | Revalidação sob demanda dos privilégios e da empresa a partir do banco | `sessaoUsuarios` |
| `sessaoPapeis.py` | Decorators por papel (administrador, função clínica, super admin) | `sessaoUsuarios`, `sessaoAutenticacao` |
| `sessaoOnboarding.py` | Decorators das rotas em onboarding e das híbridas | `sessaoUsuarios`, `sessaoAutenticacao` |
| `sessaoMfa.py` | Estado de 2FA pendente, prazo fixo e decorator das rotas do segundo fator | `sessaoUsuarios` |
| `sessaoSenha.py` | Checagem da versão da senha para leitura sensível | `sessaoUsuarios`, `sessaoAutenticacao` |

`sessaoUsuarios.py` é a base e **não importa nenhum outro módulo de sessão**, justamente para evitar ciclos.

## Estados da sessão

A sessão passa por estados guardados como flags no próprio cookie:

| Estado | Como se reconhece | Quem grava |
|---|---|---|
| Sem sessão | Sem `id_usuario` | - |
| Onboarding pendente | `onboarding_pendente=True` | Login por senha e callback do Google |
| MFA pendente | `mfa_pendente=True` + `mfa_pendente_criado_em` | `iniciar_mfa_pendente()` |
| Liberada | `id_usuario` e `id_empresa`, sem nenhuma das duas flags | Confirmação do 2FA ou conclusão do onboarding |

`mfa_pendente` deve ser gravado sempre por `iniciar_mfa_pendente()` (login por senha, login por Google e conclusão do onboarding de quem já tinha fator), nunca direto, para o timestamp acompanhar a flag.

### Prazo do `mfa_pendente`

O estado vale por **5 minutos fixos**, contados da criação. Diferente do prazo de inatividade da sessão completa, **nenhuma requisição renova esse prazo**. Isso impede que um cookie em `mfa_pendente` fique "vivo para sempre" só porque algo continua tocando a sessão (ex.: o frontend consultando o status repetidamente enquanto o usuário procura o celular para o TOTP).

Uma sessão em `mfa_pendente` sem timestamp (de antes desse controle existir) é tratada como **expirada** (fail-closed).

## Dados da sessão

O cookie guarda identidade, privilégios, função clínica e empresa, gravados no login; as rotas que pedem revalidam isso contra o banco (seção abaixo). Os getters leem esses valores sem consultar o banco, exceto `get_usuario_sessao()` e, na primeira chamada, `get_uuid_empresa_sessao()`.

| Getter | Devolve | Consulta o banco? |
|---|---|---|
| `get_id_usuario_sessao()` | Id interno do usuário, ou `None` | Não |
| `get_uuid_usuario_sessao()` | UUID do usuário, ou `None` | Não |
| `get_id_empresa_sessao()` | Id da empresa, ou `None` | Não |
| `get_uuid_empresa_sessao()` | UUID da empresa, ou `None` | Só na primeira chamada; depois fica na sessão |
| `get_is_admin_sessao()` | `True` se for administrador (padrão `False`) | Não |
| `get_funcao_clinica_sessao()` | `"medico"`, `"enfermeiro"` ou `None` | Não |
| `get_is_super_admin_sessao()` | `True` se for o admin fundador (padrão `False`) | Não |
| `get_usuario_sessao()` | Objeto `Usuario` completo e atualizado, ou `None` | **Sim**, uma vez por requisição (o resultado fica no `g`) |

`is_admin` e `funcao_clinica` são **independentes**: um admin pode ter função clínica e vice-versa. "É admin" nunca é inferido de `funcao_clinica`.

Os getters só são confiáveis **depois** de um decorator de sessão ter rodado. Para saber só a empresa (o caso mais comum, usado para filtrar dados), prefira `get_id_empresa_sessao()` a `get_usuario_sessao()`, que faz uma consulta.

### O objeto `g`

Todo decorator que libera a rota copia os dados da sessão para o `g`, para a view não reler o cookie:

| Atributo | Origem |
|---|---|
| `g.id_usuario` | Id interno |
| `g.uuid_usuario` | UUID |
| `g.id_empresa` | Empresa |
| `g.is_admin` | Administrador |
| `g.funcao_clinica` | Função clínica |
| `g.is_super_admin` | Super admin |

## Revalidação dos privilégios

O cookie guarda os privilégios como estavam no login. Para uma mudança no banco (papel retirado, usuário desativado) valer na hora, e não só no fim da sessão, os decorators de papel têm o parâmetro `revalidar`. Quando ligado, a rota relê o usuário do banco antes de checar o papel, com uma consulta por PK que o `g` reaproveita se a view também carregar o usuário:

| Situação encontrada | Efeito |
|---|---|
| Usuário removido, desativado (`status = inativo`) ou com empresa diferente da gravada na sessão | A sessão é encerrada |
| Qualquer outra | `is_admin`, `funcao_clinica` e `is_super_admin` da sessão são sincronizados com o banco (para mais ou para menos), e a checagem de papel já usa os dados atuais |

A revalidação **não roda em toda requisição**: só nas rotas cujo decorator a liga. `@requer_login` e as demais rotas não pagam essa consulta. O padrão de cada decorator:

| Decorator | `revalidar` por padrão | Motivo |
|---|---|---|
| `@requer_admin` | `True` | Tráfego baixo, privilégio alto |
| `@requer_super_admin` | `True` | Tráfego baixo, privilégio alto |
| `@requer_admin_ou_papel_clinico(...)` | `True` | Envolve o privilégio de administrador |
| `@requer_papel_clinico(...)` | `False` | Tráfego alto; ligar com `revalidar=True` onde a mudança de papel precisa valer na hora |

Sem revalidação, a rota usa os privilégios como estavam no login. Uma rota que revalida também deixa a sessão sincronizada para as demais.

---

# Decorators

## Checagem base de sessão

Comum a todos os decorators de sessão liberada, nesta ordem:

| Condição | Resultado |
|---|---|
| Sem `id_usuario` | Bloqueia: não autenticado |
| `onboarding_pendente` | Bloqueia com `onboarding_pendente` |
| `mfa_pendente` | Bloqueia com `mfa_pendente` |
| Sem `id_empresa` | Encerra a sessão e bloqueia com `sessao_invalida` |
| Nenhuma das anteriores | Segue |

## Sessão liberada e papéis

Todos executam: checagem base, revalidação (quando ligada), permissão do papel, preenchimento do `g`, view.

| Decorator | Exige | Revalida por padrão | Observação |
|---|---|---|---|
| `@requer_login` | Sessão liberada | Não | Só a checagem base |
| `@requer_admin` | `is_admin` | Sim | Independe de função clínica |
| `@requer_papel_clinico("medico", ...)` | Função clínica entre as informadas | Não | Independe de `is_admin` |
| `@requer_admin_ou_papel_clinico("medico", ...)` | `is_admin` **ou** uma das funções | Sim | OR |
| `@requer_super_admin` | `is_admin` **e** `is_super_admin` | Sim | Sempre `g.is_super_admin = True` na view |
| `@requer_senha_atualizada("acao")` | Sessão liberada + senha não alterada desde o login | Não | Ver seção própria |

O parâmetro `revalidar` pode ser trocado em qualquer decorator de papel. Os de administrador seguem aceitando o uso sem parênteses:

```python
@requer_admin                          # revalida (padrão)
@requer_admin(revalidar=False)         # sem consulta ao banco
@requer_papel_clinico("medico")        # não revalida (padrão)
@requer_papel_clinico("medico", revalidar=True)
```

**AND versus OR.** Empilhar `@requer_admin` com `@requer_papel_clinico(...)` exige as **duas** condições. Para liberar a rota a qualquer um dos dois, usar `@requer_admin_ou_papel_clinico(...)`.

**Super admin versus checagem por alvo.** `@requer_super_admin` serve quando a exigência vale para a rota inteira (ex.: criar um novo admin). Quando depende do **alvo** da operação (ex.: atualizar ou desativar um usuário que pode ou não ser admin), usa-se `@requer_admin` na rota e a checagem fina no service com `g.is_super_admin`, porque o decorator não conhece o alvo antes de a rota rodar.

## Rotas de onboarding e híbridas

Atendem uma sessão que ainda **não está completa**, então **não preenchem o `g`** quando há onboarding pendente (faltam `id_empresa` e os privilégios).

| Decorator | Aceita | Preenche `g`? |
|---|---|---|
| `@onboarding_pendente_required` | Só sessão com `onboarding_pendente` | Não |
| `@requer_login_ou_onboarding_pendente` | Sessão com `onboarding_pendente` **ou** sessão liberada | Só no ramo liberado |

As rotas híbridas (cadastro de WebAuthn e de TOTP) devem obter o usuário por `get_usuario_sessao()` ou `get_id_usuario_sessao()`, nunca por `g.id_empresa`, que não existe no ramo de onboarding.

## Rotas do segundo fator

| Decorator | Aceita |
|---|---|
| `@mfa_pendente_required` | Só sessão com `mfa_pendente` dentro do prazo fixo de 5 minutos |

Se o prazo vencer, a sessão é limpa e o usuário precisa refazer o login.

## Leitura sensível: `@requer_senha_atualizada`

Cobre uma categoria intermediária que nem o step-up (que é para escrita) nem o prazo de inatividade cobrem bem sozinhos: a **leitura de dados clínicos de paciente**. Uma sessão sequestrada poderia continuar lendo prontuário pelo resto do prazo do dono mesmo depois de ele ter trocado a senha.

1. A sessão guarda `senha_versao`, gravada no login (senha, Google e confirmação de 2FA).
2. A versão no banco é incrementada toda vez que a senha muda (troca pelo próprio usuário ou reset por admin).
3. Na rota decorada, o decorator compara as duas com **uma consulta indexada por PK**, só da coluna da versão.
4. Se a versão da sessão for diferente da atual: registra o acesso negado (a `acao` informada no decorator entra como recurso, com o motivo `sessao_com_senha_desatualizada`), **encerra a sessão** e nega o acesso.

Regras:

- Roda **só nas rotas decoradas**, nunca no login comum, para não custar uma consulta em todo o tráfego autenticado.
- Sessão **sem** `senha_versao` (aberta antes do controle existir) passa: o fail-open é intencional, para não deslogar todo mundo na entrada em produção.
- É passivo: não pede nada ao usuário, só verifica e registra quando nega. Pensado para `GET`.
- Diferente de `@acao_sensivel` (escrita, com log de mutação) e do step-up (reautenticação ativa antes de agir).

## Formato das respostas de bloqueio

Todos os decorators do pacote respondem com o mesmo corpo JSON:

| Campo | Conteúdo |
|---|---|
| `status` | Sempre `"error"` |
| `erro` | Código estável, para o frontend decidir o que fazer |
| `message` | Texto pronto para exibir ao usuário |

Códigos usados em `erro`:

| Código | Quando |
|---|---|
| `nao_autenticado` | Não há sessão iniciada |
| `onboarding_pendente` | A sessão ainda está no onboarding |
| `mfa_pendente` | A sessão aguarda o segundo fator |
| `sem_permissao` | O usuário não tem o papel exigido |
| `sessao_invalida` | A sessão não está no estado esperado pela rota, expirou ou deixou de valer na revalidação |
| `sessao_invalida_senha_alterada` | A senha mudou desde o login (só em `@requer_senha_atualizada`) |