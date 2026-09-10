# Formas de Usuário

Documentação de como o sistema distingue o que um usuário **é** (profissão clínica) do que ele **pode fazer administrativamente** (permissão de admin), cobrindo o model, a sessão, os decorators de autorização, e a ação sensível de alterar essas duas dimensões.

---

# Contexto e conceitos

## Visão geral

Um usuário no bion é descrito por duas perguntas independentes, nunca uma única categoria:

1. **"Ele atende clinicamente?"** — resposta em `funcao_clinica`: `"medico"`, `"enfermeiro"` ou `None`.
2. **"Ele administra o sistema?"** — resposta em `is_admin`: `True` ou `False`.

As duas perguntas têm respostas independentes. Um usuário pode ser médico e não-admin (o caso mais comum), admin puro sem nenhuma função clínica (o dono de um hospital que só gerencia), ou **as duas coisas ao mesmo tempo** — o dono de uma clínica pequena que também atende pacientes. Não existe uma terceira opção "tipo de usuário" que resuma isso num valor só: essas duas perguntas nunca colapsam numa categoria única.

Isso é diferente de um modelo anterior do sistema, onde um único campo (`tipo_usuario`) respondia `"medico"`, `"enfermeiro"` ou `"admin"` — um valor de cada vez, mutuamente exclusivo. Esse modelo não conseguia representar alguém que fosse as duas coisas, e foi substituído deliberadamente, sem campo de compatibilidade: todo código que hoje pergunta "isso é admin?" ou "qual a função clínica?" precisa perguntar cada coisa separadamente.

## As duas dimensões

### Função clínica (`funcao_clinica`)

Não é uma coluna do `Usuario` — é uma property calculada a partir de `PapelProfissional`, uma tabela própria (`papel_profissional`) que guarda CRM/COREN, UF do conselho, especialidade e RQE. Um usuário pode ter vários registros de `PapelProfissional` ao longo do tempo (histórico preservado — trocar de enfermeiro para médico desativa o papel antigo em vez de apagar), mas só um **ativo** por vez.

`funcao_clinica` lê esse papel ativo e devolve `"medico"`, `"enfermeiro"`, ou `None` se não houver nenhum papel ativo (o caso de um admin puro, ou de alguém que perdeu a função clínica). Nunca retorna `"admin"` — essa palavra não pertence a este eixo.

```python
usuario.funcao_clinica  # "medico" | "enfermeiro" | None
usuario.papel_ativo()   # instância de PapelProfissional, ou None
```

### Permissão administrativa (`is_admin`)

Coluna booleana direta em `Usuario`. Não depende de função clínica, não é calculada — é um fato próprio do usuário. Concede acesso a rotas de gerenciamento (criar/editar/desativar outros usuários, ver configurações da empresa).

Existe uma segunda flag, `is_super_admin`, que distingue o admin "fundador" (criado junto com a empresa) dos demais admins criados depois por ele. Só o super admin pode criar novos admins ou alterar (editar/desativar/ativar) outro admin; um admin comum não mexe em nenhum admin, nem nele mesmo nesse sentido. O super admin nunca pode ser rebaixado ou desativado, por ninguém — nem por ele mesmo.

## Por que as duas nunca se misturam

A regra de design central: **nenhum código deve inferir uma dimensão a partir da outra**. `is_admin=True` não diz nada sobre `funcao_clinica`, e vice-versa. Isso vale tanto para leitura quanto para escrita:

- Autorizar uma rota administrativa nunca olha `funcao_clinica`.
- Autorizar uma rota clínica (ex: abrir um atendimento) nunca olha `is_admin`.
- Promover ou rebaixar `is_admin` **nunca** acontece por edição de cadastro — só no momento de criação de um novo usuário, e só pelo super admin. Um admin não vira "não-admin" nem um médico comum "vira admin" editando o próprio cadastro ou o de outra pessoa.
- Trocar `funcao_clinica` (ex: enfermeiro virando médico, ou perdendo a função clínica) continua permitido via edição normal — é um eixo independente, com suas próprias regras (exige CRM/COREN completos ao trocar para médico/enfermeiro).

## A invariante: todo usuário precisa ser uma coisa ou outra

Ainda que independentes, as duas dimensões têm uma regra de combinação: **um usuário nunca pode ter `is_admin=False` e `funcao_clinica=None` ao mesmo tempo**. Isso criaria alguém sem qualquer acesso ao sistema — nem rotas administrativas, nem rotas clínicas o reconheceriam.

Essa invariante é verificada tanto na criação quanto na edição:

- **No cadastro**, é uma regra de validação simples: se `eh_admin` vier `False` (ou ausente) e `tipo_papel` vier vazio, o cadastro é rejeitado.
- **Na edição**, é mais sutil, porque um payload de atualização parcial pode não mexer em nenhum dos dois campos (só trocar telefone, por exemplo) — nesse caso a checagem é sobre o **resultado final**, depois de mesclar o payload com o que o usuário já tinha. Se esse resultado ficaria sem admin e sem papel, a edição é bloqueada — mesmo que o payload não tenha tocado nesses campos diretamente. Isso é deliberado: existe para pegar tanto tentativas diretas quanto dados legados que já estejam inconsistentes, forçando a correção antes de qualquer outra edição no cadastro.

## Como a sessão representa isso

No login (por senha ou por Google), a sessão grava as duas dimensões como chaves independentes:

```python
session["is_admin"] = usuario.is_admin
session["funcao_clinica"] = usuario.funcao_clinica
```

Isso é calculado uma vez, no momento do login, e cacheado — nenhuma rota volta ao banco para reconferir a cada requisição. Isso tem uma implicação prática: se a função clínica ou a permissão de admin de alguém forem alteradas por outra pessoa enquanto a sessão dele está ativa, a sessão antiga continua "achando" o valor de antes até o próximo login. Não é um bug — é uma característica de qualquer sessão cacheada, e é o motivo pelo qual alterar essas duas dimensões é tratado como ação sensível (ver seção própria).

## Autorização de rota: três formas de checar

Como as duas dimensões são independentes, existem três decorators diferentes para proteger uma rota, dependendo do que ela realmente exige:

| Decorator | Checa | Uso |
|---|---|---|
| `requer_admin` | `session["is_admin"] is True` | Rotas de gerenciamento — criar/editar usuário, configurações da empresa |
| `requer_papel_clinico("medico")` | `session["funcao_clinica"]` está entre os papéis informados | Rotas clínicas — abrir atendimento, prescrever |
| `requer_admin_ou_papel_clinico("medico")` | `is_admin` OU a função clínica bate | Rotas que qualquer um dos dois perfis pode acessar |

O terceiro existe porque simplesmente empilhar `@requer_admin` com `@requer_papel_clinico(...)` exigiria as **duas** condições ao mesmo tempo (mais restritivo do que geralmente pretendido) — empilhar decorators é sempre E lógico, nunca OU. Quando uma rota deveria liberar para "admin OU médico", o terceiro decorator expressa isso diretamente, sem empilhamento.

Um admin que também é médico passa pelos três tipos de rota normalmente — `requer_admin` e `requer_papel_clinico("medico")` sozinhos já o autorizam, cada um checando sua própria dimensão, sem precisar de tratamento especial.

## Alterar essas dimensões é ação sensível

Mudar `is_admin` ou `funcao_clinica` de alguém, via edição de cadastro, exige **step-up** — a mesma reconfirmação de identidade descrita no fluxo de autenticação, usando `X-Stepup-Token`. A rota de atualização de usuário também edita campos triviais (telefone, email), que não deveriam pedir essa fricção — então a exigência é condicional ao conteúdo do payload, não uma trava fixa na rota inteira:

```python
mexe_em_campo_sensivel = "eh_admin" in dados or "tipo_papel" in dados
if mexe_em_campo_sensivel and not token_recente_valido("alterar_papel_usuario"):
    # 403 confirmacao_requerida
```

Isso reaproveita a mesma função (`token_recente_valido`) que o decorator `requer_confirmacao_recente` usa por baixo — extraída para ser chamada tanto de forma automática (decorando uma rota inteira, como `desativar()`) quanto condicional (checando dentro da view, como aqui).

**Por que isso é tratado como sensível**: diferente de um telefone errado (efeito visível e imediato), um papel alterado incorretamente tem efeito silencioso e distribuído — um médico que perde a função clínica no meio do expediente continua parecendo médico para a sessão dele (cacheada), mas some de qualquer lista nova de "médicos disponíveis" montada a partir do banco a partir dali. O custo de errar essa mudança não aparece na hora, aparece depois, em outro lugar do sistema.

## O que isso não resolve (ainda)

Esse fluxo cobre a barreira de confirmação, mas **não gera um registro de auditoria** (`LogAlteracao`) especificamente para essa ação — decisão deliberada de manter simples por enquanto. Se um médico tiver a função clínica removida enquanto conduz um atendimento em andamento, o sistema não impede nem avisa sobre esse conflito no momento em que ele acontece; a trilha de "quem era o quê, quando" existe de forma geral (via auditoria de alterações de outros domínios), mas não há checagem cruzada com atendimentos abertos no momento da troca.

---

# Médico e enfermeiro: hierarquia dentro de `funcao_clinica`

A seção anterior trata `funcao_clinica` como um valor entre outros (`"medico"`, `"enfermeiro"`, `None`) para fins de admin vs. clínico. Mas dentro do próprio eixo clínico, os dois valores não são paralelos — são uma hierarquia de capacidade, e isso tem consequência direta em como o ciclo de vida da Consulta é modelado, não só em quem pode chamar qual rota.

## Médico é superset de enfermeiro, nunca o contrário

A regra: **tudo que um enfermeiro pode fazer clinicamente, um médico também pode — a via inversa não existe.** Isso não é uma preferência de UX, é uma decisão de modelagem que aparece diretamente nas permissões de rota do domínio de Atendimento:

```python
@bp_atendimento.post("/consulta/<uuid_consulta>/abrir-triagem")
@requer_papel("medico", "enfermeiro")
def abrir_triagem(uuid_consulta): ...

@bp_atendimento.post("/consulta/<uuid_consulta>/abrir-avaliacao-medica")
@requer_papel("medico")
def abrir_avaliacao_medica(uuid_consulta): ...
```

A etapa de triagem aceita ambos; a etapa de avaliação médica aceita só médico. Não existe rota clínica em que `enfermeiro` seja aceito e `medico` não — a hierarquia é assimétrica por construção, não por lista de papéis coincidentemente sobreposta.

## Por que isso importa: nem toda clínica tem enfermeiro

O modelo do ciclo de Consulta (triagem → avaliação médica → desfecho) foi originalmente pensado assumindo que sempre existe um enfermeiro fazendo a triagem enquanto o médico foca na avaliação — um fluxo com paralelismo real entre duas pessoas. Isso não é universal: o produto atende tanto hospitais quanto clínicas pequenas, e em clínicas pequenas o médico frequentemente **é** quem faz a triagem também, seja porque não há enfermeiro no quadro, seja porque o volume não justifica.

Como médico é superset de enfermeiro na permissão de rota, isso já funciona sem nenhuma mudança de autorização: o mesmo usuário com `funcao_clinica="medico"` pode chamar `abrir-triagem` e, em seguida, `abrir-avaliacao-medica`, para a mesma Consulta.

## A etapa de triagem continua obrigatória — só quem a faz que varia

Decisão importante, e não óbvia à primeira vista: mesmo quando é o mesmo médico fazendo as duas etapas, **a triagem não é pulada nem fundida com a avaliação médica**. `AtendimentoService.abrir_avaliacao_medica` bloqueia a abertura se não existir uma triagem já finalizada para aquela Consulta, independentemente de quem a tenha feito:

```python
triagem_finalizada = any(
    a.tipo_atendimento == "triagem" and a.status == "finalizado"
    for a in atendimentos
)
if not triagem_finalizada:
    raise ConflictoError(
        "É necessário finalizar a triagem desta Consulta antes de abrir a avaliação médica."
    )
```

A razão para manter essa rigidez, mesmo sem enfermeiro: triagem e avaliação médica não são a mesma pergunta clínica em sequência — são dois protocolos com objetivos diferentes. A triagem responde "esse paciente corre risco agora, em que ordem deveria ser visto" (discriminação/urgência, ex: MTS); a avaliação médica responde "o que esse paciente tem, o que fazer" (diagnóstico). Fundir as duas etapas apagaria essa distinção de raciocínio clínico, mesmo que a distinção de mão de obra deixe de existir. Por isso a solução para "não tem enfermeiro" não é remover a etapa — é permitir que o mesmo profissional a percorra duas vezes, como dois momentos de raciocínio distintos, ainda que consecutivos.

Isso também mantém a integridade dos dados que dependem da etapa de triagem existir como registro próprio — sinais vitais, tempo desde o início dos sintomas, inputs do protocolo de risco — sem depender de haver dois profissionais diferentes para isso.

## Duas travas de sequência, simétricas

Como consequência direta da obrigatoriedade acima, `AtendimentoService` também impede duplicar ou pular a etapa nos dois sentidos:

- `abrir_triagem` recusa (`ConflictoError`) se já existir uma triagem em-andamento ou já finalizada para a Consulta — não é permitido reabrir nem duplicar a etapa, mesmo com o mesmo profissional tentando de novo.
- `abrir_avaliacao_medica` recusa se a triagem não estiver finalizada, e também recusa abrir uma segunda avaliação médica em-andamento.

O resultado é uma sequência rígida e previsível — `abrir-triagem → finalizar → abrir-avaliacao-medica → finalizar` — válida tanto no fluxo com enfermeiro quanto no fluxo só-médico, sem ramificação condicional no back para o caso "sem enfermeiro". O que muda entre os dois fluxos é exclusivamente `realizado_por` ser ou não a mesma pessoa nos dois Atendimentos; nenhuma validação de sequência olha para esse campo.

## Implicação de UX, não de dado

A rigidez da sequência é deliberadamente uma decisão de back-end, não de experiência do usuário. Quando o mesmo médico faz as duas etapas sem pausa real entre elas, a exigência de "abrir → finalizar → abrir → finalizar" pode parecer trabalho duplicado de clique — mas isso é um problema de interface a ser resolvido no front (ex: uma tela única que dispara as duas chamadas em sequência sem expor a costura), não uma razão para afrouxar a validação no back. Fluidez de tela e rigidez de estrutura não são objetivos concorrentes aqui.

## Estatísticas: essa flexibilidade precisa ser enxergada, não só permitida

Permitir que o mesmo profissional faça as duas etapas introduz uma dimensão nova que as métricas agregadas por `tipo_atendimento` (tempo médio de triagem, tempo médio de avaliação médica) não enxergavam antes: um médico sozinho tende a ter um comportamento de tempo sistematicamente diferente de um enfermeiro dedicado fazendo a mesma etapa — não porque um seja "melhor", mas porque a motivação de cada etapa muda quando não há paralelismo a ganhar. Misturar as duas populações numa média só, sem sinalizar isso, produz um número que não representa bem nenhum dos dois grupos. Por isso a métrica de tempo médio por tipo tem um complemento que segmenta por "mesmo profissional fez as duas etapas" vs. "profissionais diferentes", exibido como aviso apenas quando a proporção de um dos grupos é alta o suficiente para distorcer a leitura combinada — não como uma segunda métrica sempre visível.