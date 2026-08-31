# Fluxo de Auditoria

Documentação do sistema de auditoria (trilha de logs), cobrindo o que é
registrado, como se relaciona com step-up authentication, os dois
decorators que orquestram o registro, e as garantias de atomicidade e
imutabilidade envolvidas.

---

# Contexto e conceitos

## Visão geral

Auditoria garante duas coisas: que toda ação relevante sobre dados
sensíveis fique registrada de forma verdadeira (quem fez, o quê, quando),
e que esse registro não possa ser alterado ou apagado depois — nem por
quem o gerou, nem por um administrador. O sistema separa dois tipos de
evento em modelos distintos, porque representam fatos diferentes:

1. **Acesso** (`LogAcesso`) — alguém viu, exportou ou tocou um recurso.
   Cobre `leitura`, `escrita`, `exclusao-logica` e `exportacao` como
   naturezas de operação, mais o resultado (`sucesso`,
   `falha-autenticacao`, `acesso-negado`, `timeout`).

2. **Alteração** (`LogAlteracao`) — um registro específico de uma tabela
   mudou. Guarda `tabela_origem`, o registro afetado (`id_registro` +
   `uuid_registro`), a operação (`INSERT`/`UPDATE`/`DELETE`) e,
   opcionalmente, o diff campo a campo (`campo_alterado`,
   `valor_anterior`, `valor_novo`) mais uma `justificativa` textual.

Ambos são **append-only**: os repositories correspondentes sempre
retornam `False` em `delete()`, e `AuditoriaService.excluir()` lança
`PermissaoNegadaError` incondicionalmente. Isso não é validação de
permissão — é a ausência estrutural de qualquer caminho de exclusão,
reforçada em três camadas (repository, service, e a ausência de rota
`DELETE` no controller).

## Relação com step-up: por que os dois domínios se encontram

Um log só tem valor se a autoria for verdadeira. Sem reconfirmação de
identidade, o `id_usuario` gravado num `LogAlteracao` poderia ser de uma
sessão sequestrada ou deixada aberta — o log estaria tecnicamente
completo, mas mentindo sobre quem realmente agiu.

Por isso, toda ação sensível (destrutiva ou irreversível: excluir
prontuário, alterar prescrição, conceder acesso admin) passa primeiro
pelo step-up (`step_up.py` — ver documento de autenticação) antes de
gerar seu log. O step-up cumpre dois papéis em relação à auditoria:

- **Garantir a autoria** — só depois de reconfirmar via WebAuthn ou
  senha+Google é que a ação roda, então o `id_usuario` do log corresponde
  a quem de fato confirmou, não só a quem estava logado.
- **Tornar o usuário ciente de que a ação será registrada** — o modal de
  step-up (`stepupModal.html`) descreve a ação em texto claro antes de
  pedir a confirmação. O usuário sabe, no momento em que confirma, que
  está prestes a fazer algo que vai ficar na trilha de auditoria.

O step-up, sozinho, **não grava nada em `LogAcesso`/`LogAlteracao`** — ele
só garante que quem está do outro lado é o dono da conta. A gravação do
log é responsabilidade de um decorator próprio (`acao_sensivel`, ver
abaixo), que encapsula o step-up e o registro do log como uma coisa só,
para que não seja estruturalmente possível confirmar uma ação sensível
sem ela ficar auditada.

## Dois decorators, dois níveis de garantia

Nem toda ação registrada em log precisa de step-up. Ler um prontuário é
sensível o bastante para merecer trilha de auditoria, mas pedir
reconfirmação de identidade a cada leitura seria fricção sem ganho real
de segurança — o usuário já está numa sessão autenticada válida. Por
isso existem dois decorators, para dois casos de uso deliberadamente
diferentes:

| Decorator | Cobre | Exige step-up? | Atômico com a ação? |
|---|---|---|---|
| `acao_sensivel` | Escrita/exclusão (`LogAlteracao`) | Sim | Sim — commit único |
| `acesso_auditado` | Leitura sensível (`LogAcesso`) | Não | Não aplicável (leitura não altera dados) |

Essa divisão é uma decisão de produto: reconfirmação de identidade fica
reservada para ações destrutivas/irreversíveis. Auditoria (o log em si)
acontece nos dois casos — saber "quem viu o quê e quando" tem valor de
compliance mesmo sem reconfirmação.

## Atomicidade: por que a alteração e o log vivem na mesma transação

Um log poderia divergir da realidade de duas formas opostas, e as duas
são igualmente inaceitáveis para uma trilha de auditoria:

- **Ação sem log** — a alteração é persistida, mas o registro do log
  falha depois (ex.: erro de conexão) — resultado: uma ação real sem
  nenhum rastro.
- **Log sem ação** — o log é persistido, mas a alteração real falha
  depois — resultado: um registro descrevendo algo que nunca aconteceu.

Para evitar os dois cenários, `acao_sensivel` exige que a alteração e o
log entrem na **mesma transação de banco**, com um único `commit()` no
fim. Isso significa que:

- Os repositories de auditoria (`LogAcessoRepository`,
  `LogAlteracaoRepository`) **não commitam sozinhos** — só fazem
  `db.session.add(...)`. Commit é responsabilidade de quem orquestra a
  transação (o decorator).
- A view decorada com `acao_sensivel` **também não pode commitar
  sozinha**. Se o repository da entidade alterada tiver um parâmetro tipo
  `save(entity, commit=True)`, a view precisa chamar com `commit=False`
  (que tipicamente faz `add()` + `flush()` — o `flush()` é necessário
  quando a view depende do ID gerado por autoincrement para montar os
  detalhes que devolve ao decorator).
- Se qualquer parte falhar — a view lança exceção, ou faltam campos
  obrigatórios nos detalhes retornados — o decorator faz
  `db.session.rollback()`, desfazendo tudo que estava pendente na sessão.
  Não fica alteração parcial persistida sem o log correspondente.

---

# Fluxos

## Ação sensível (escrita/exclusão): `acao_sensivel`

1. A rota é decorada com `@acao_sensivel("acao_identificadora", tabela="nome_da_tabela")`.
2. O decorator chama `StepUp.requer_confirmacao_recente(acao)` por baixo
   — mesmo mecanismo e mesmo contrato HTTP do step-up já documentado
   (`403 confirmacao_requerida` se não houver token válido no header
   `X-Stepup-Token`). O frontend (`stepUp.js`) não precisa de nenhuma
   alteração para isso funcionar — o contrato de requisição/resposta que
   ele já espera continua idêntico.
3. Identidade confirmada, a view roda. A view faz suas alterações via
   `db.session.add(...)` / repository com `commit=False`, e retorna uma
   tupla `(resposta_flask, detalhes)`, onde `detalhes` é um dict com pelo
   menos `id_registro` e `uuid_registro` (e opcionalmente `operacao`,
   `tabela_origem`, `campo_alterado`, `valor_anterior`, `valor_novo`,
   `justificativa`).
4. O decorator chama `AuditoriaService.registrar_alteracao(...)` com
   esses detalhes, mais `id_usuario` (da sessão) e `ip_origem` (da
   requisição).
5. Um único `db.session.commit()` persiste a alteração da view e o log
   juntos. Se a view não retornar `id_registro`/`uuid_registro`, ou se
   qualquer etapa lançar exceção, `db.session.rollback()` desfaz tudo.

Se a view lançar exceção antes de retornar, nada é logado — não faria
sentido registrar uma alteração que não aconteceu. Isso é diferente de
logar uma *tentativa* de acesso negado, que é outro caso de uso, coberto
por `resultado="acesso-negado"` em `registrar_acesso` (ver abaixo) — não
por este decorator.

## Acesso sensível (leitura): `acesso_auditado`

1. A rota é decorada com `@acesso_auditado("nome_do_recurso", operacao="leitura")`.
   Sem step-up — a sessão autenticada já basta.
2. A view roda normalmente e retorna sua resposta (ou, opcionalmente,
   `(resposta, detalhes)` se quiser especificar `uuid_paciente` ou
   sobrescrever `resultado`/`operacao` dinamicamente).
3. Só depois da view responder com sucesso, o decorator chama
   `AuditoriaService.registrar_acesso(...)` e commita.

Se a view lançar exceção, nada é logado aqui — a exceção sobe
normalmente para o error handler padrão da aplicação.

## Token de step-up: reuso entre ações e chamadas concorrentes

Um `StepUpToken` nunca cobre mais de uma ação, mesmo que duas rotas
usem o mesmo identificador de `acao`. Cada chamada a `pedirConfirmacao(acao)`
no frontend gera uma nova requisição a `/stepup/iniciar`, e cada uma
recebe um token distinto (`token` é `unique=True` no banco). O token é
consumido (apagado) assim que uma rota o usa com sucesso — uma segunda
tentativa de reuso, seja por bug de frontend ou replay manual, não
encontra mais token válido e recebe `403 confirmacao_requerida` de novo.

Isso vale mesmo para ações sobre tabelas diferentes: não existe (nem
deveria existir) uma noção de "uma confirmação vale para duas ações". Se
um fluxo naturalmente encadeia múltiplas ações sensíveis em sequência,
cada uma exige sua própria chamada a `pedirConfirmacao()` e gera seu
próprio token — reconfirmação de identidade é por ação, não por janela de
tempo desde a última prova.

**Duas camadas de proteção separadas, contra dois problemas diferentes:**

- **Frontend (`stepUp.js`) — serialização de UI.** `pedirConfirmacao()`
  mantém uma fila interna (`filaConfirmacao`): se o código da aplicação
  disparar dois `pedirConfirmacao(...)` sem `await` entre eles (ex.: dois
  cliques quase simultâneos em botões diferentes), a segunda chamada só
  abre seu modal depois que a primeira resolver ou rejeitar. Isso não é
  proteção contra ataque — é necessidade de UI: o modal é um único
  overlay compartilhado no DOM (`garantirModalCarregado`), e duas
  confirmações abertas ao mesmo tempo pisariam no estado visual e nos
  listeners uma da outra. O resultado prático é que, do ponto de vista de
  quem chama, duas ações "ao mesmo tempo" viram duas confirmações em
  sequência, cada uma com seu próprio token — nunca duas em paralelo.
- **Backend (`step_up.py`) — atomicidade do consumo do token.** A
  serialização do frontend não substitui essa garantia: ela impede que
  *a mesma aba* abra dois modais em paralelo, mas não impede que duas
  requisições cheguem simultaneamente ao backend por outros caminhos
  (duas abas, replay manual, uma extensão maliciosa). Continua
  dependendo de o backend consumir o token de forma atômica (ex.:
  `DELETE` condicional) — ver pendência abaixo.

---

# Modelos

## `LogAcesso`

| Campo | Tipo | Observação |
|---|---|---|
| `uuid` | string(36) | Identificador público, não sequencial |
| `id_empresa` | FK → `empresas` | Preenchido no momento do evento, não derivado via join — evita que o log "mude de dono" se o vínculo empresa/usuário mudar depois |
| `id_usuario` | FK → `usuarios` | Obrigatório |
| `recurso_acessado` | string(255) | Nome livre do recurso |
| `operacao` | enum | `leitura`, `escrita`, `exclusao-logica`, `exportacao` |
| `resultado` | enum | `sucesso`, `falha-autenticacao`, `acesso-negado`, `timeout` |
| `uuid_paciente` | string(36), opcional | Referência leve, sem FK — não acopla o domínio de auditoria ao domínio clínico |

Índices: `(id_empresa, data_hora)` e `(id_usuario, data_hora)` — dão
suporte à navegação em funil (empresa → usuário → data) sem forçar table
scan em tabela grande.

Nome e cargo do usuário **não são armazenados no log** — são consultados
via join com `Usuario` no momento da exibição. Um log deveria refletir o
fato do evento (o quê, quando, resultado), não um snapshot de metadado do
usuário; cargo histórico, se algum dia for necessário, é uma decisão de
produto separada, não resolvida por duplicar o dado aqui.

## `LogAlteracao`

| Campo | Tipo | Observação |
|---|---|---|
| `uuid` | string(36) | Identificador público |
| `id_empresa` | FK → `empresas` | Mesma lógica do `LogAcesso` — pode ficar `NULL` se `alterado_por` também for nulo (alteração sem usuário vinculado) |
| `tabela_origem` / `id_registro` / `uuid_registro` | — | Aponta para o registro afetado em outro domínio |
| `operacao` | enum | `INSERT`, `UPDATE`, `DELETE` |
| `campo_alterado` / `valor_anterior` / `valor_novo` | opcional | Diff campo a campo, quando a view fornece |
| `alterado_por` | FK → `usuarios`, opcional | Pode ser nulo (ex.: alteração de sistema, sem ator humano) |
| `justificativa` | text, opcional | — |

Índices: `(id_empresa, alterado_em)`, `(alterado_por, alterado_em)`,
`(uuid_registro, alterado_em)`.

---

# Pontos ainda em aberto

Registrado aqui para não ficar implícito: as decisões abaixo foram
discutidas mas dependem de código real de cada domínio (prontuário,
prescrição, usuários) para serem concluídas — este documento descreve o
mecanismo, não o estado de aplicação em cada rota específica.

- **Nenhuma rota real ainda usa `acao_sensivel`/`acesso_auditado`** — os
  decorators existem, mas aplicar em cada view (excluir prontuário,
  alterar prescrição, conceder admin, visualizar prontuário) é trabalho
  view a view, incluindo trocar `commit=True` por `commit=False` em cada
  `save()` que a view chama internamente.
- **Corrida na consumo do token de step-up** — depende de o
  `step_up.py` consumir o token de forma atômica (ex.: `DELETE`
  condicional) e não em dois passos (`SELECT` seguido de `DELETE`), para
  que duas requisições simultâneas com o mesmo token não possam ambas
  passar. Não confirmado ainda a partir do código.
- **Paginação e retenção** — `find_all()` hoje usa `LIMIT` fixo (500/200),
  sem cursor. Filtro por período (funil empresa → usuário → data, com
  janela deslizante) ainda não tem endpoint implementado.