# Fluxo de Auditoria

Documentação da trilha de auditoria do Bion, cobrindo o registro de acessos e de alterações de dados (escrita, exclusão e leitura sensível), a reconfirmação de identidade nas ações sensíveis e as consultas feitas pelos administradores.

---

# Contexto e conceitos

## Visão geral

A auditoria responde a duas perguntas: **quem leu** dados sensíveis e **quem alterou** dados, quando, de onde e com qual justificativa. O sistema mantém dois logs com finalidades diferentes:

| Log | Registra | Gravado por | Tabela/modelo |
|---|---|---|---|
| Log de acesso | Leituras sensíveis, exportações e acessos negados | `@acesso_auditado` (e `registrar_acesso_negado`) | `LogAcesso` |
| Log de alteração | Escritas e exclusões: o que mudou, valor anterior e novo | `@acao_sensivel` | `LogAlteracao` |

As consultas aos logs são exclusivas de administradores (`@requer_admin`), sempre dentro da empresa da sessão.

## Camadas

| Camada | Arquivo | Responsabilidade |
|---|---|---|
| Decorators | `acaoSensivel.py` | Aplicar step-up, interceptar a resposta da view, chamar o service e fazer o commit |
| Controller | `controller.py` | Ler e validar parâmetros HTTP, montar a resposta padronizada |
| Service | `service.py` | Regras de negócio: validações, resolução do período, montagem do resumo |
| Repository | `repository.py` | Queries, filtros, paginação |

## Princípios

- **Imutabilidade**: os logs são append-only. Não existe atualização nem exclusão; `AuditoriaService.excluir` sempre levanta `PermissaoNegadaError`, e `delete` nos repositories sempre devolve `False`.
- **Transação única**: gravar um log só adiciona a entidade à sessão. O commit é feito uma vez, pelo decorator, junto com a ação auditada. Se algo falhar, tudo é desfeito, inclusive a alteração.
- **Isolamento por empresa**: toda consulta exige `id_empresa` (vindo da sessão) e o repository o aplica em todas as queries.
- **Sem id interno para fora**: nenhuma entrada ou saída pública usa o `id` sequencial do usuário, só `uuid`. O id interno aparece na gravação (vindo da sessão autenticada) e dentro das queries.
- **`acao` é texto livre** por enquanto (ex.: `"editar_paciente"`). O vocabulário ainda é definido a cada uso dos decorators.

## Vocabulários de operação

`LogAcesso.operacao` usa categorias de negócio. `LogAlteracao.operacao` guarda o que o SQL de fato fez. Para o mesmo filtro da UI servir aos dois, o repository **traduz** a categoria na consulta, sem gravar a tradução.

| Categoria de negócio | `LogAcesso.operacao` | `LogAlteracao.operacao` (traduzido) |
|---|---|---|
| `leitura` | sim | sem equivalente (filtro resulta em lista vazia) |
| `escrita` | sim | `INSERT`, `UPDATE` |
| `exclusao-logica` | sim | `DELETE` |
| `exportacao` | sim | sem equivalente (filtro resulta em lista vazia) |

Valores estruturais (`INSERT`, `UPDATE`, `DELETE`) também são aceitos direto em `LogAlteracao`. Um filtro sem equivalente SQL nunca é ignorado: ele devolve vazio, em vez de devolver tudo.

`LogAcesso.resultado` aceita: `sucesso`, `falha-autenticacao`, `acesso-negado`, `timeout`.

---

# Gravação

## Escrita e exclusão sensíveis: `@acao_sensivel`

```
@acao_sensivel("editar_paciente", tabela="paciente")
def editar(...):
    ...
    return resposta, {"id_registro": ..., "uuid_registro": ..., ...}
```

Fluxo de uma requisição:

1. **Step-up**: o decorator `StepUp.requer_confirmacao_recente(acao)` exige o token de uso único no header `X-Stepup-Token`. Sem token válido, a rota responde `403 confirmacao_requerida` e a view nem executa. O token vale 180s, é vinculado a (usuário, ação) e é apagado ao ser lido, mesmo que a ação falhe depois (ver `auth.md`).
2. **View**: executa a alteração **sem** `db.session.commit()` e devolve `(resposta, detalhes)`.
3. **Validação dos detalhes**: se faltar `id_registro` ou `uuid_registro`, levanta `ValueError` (erro de programação da view).
4. **Log**: `registrar_alteracao` monta o `LogAlteracao` com empresa, usuário e IP da sessão e o adiciona à sessão. Em `DELETE`, a `justificativa` é obrigatória; sem ela levanta `DadosInvalidosError`.
5. **Commit único**: alteração e log são confirmados juntos.
6. **Falha em qualquer ponto** (view ou log): `rollback` de tudo e a exceção segue adiante.

Chaves do dicionário `detalhes`:

| Chave | Obrigatória | Padrão | Significado |
|---|---|---|---|
| `id_registro` | sim | - | Id interno do registro alterado |
| `uuid_registro` | sim | - | UUID do registro alterado |
| `tabela_origem` | não | `tabela` do decorator | Tabela afetada, quando difere da padrão |
| `operacao` | não | `"UPDATE"` | `INSERT`, `UPDATE` ou `DELETE` |
| `campo_alterado` | não | `None` | Campo que mudou |
| `valor_anterior` / `valor_novo` | não | `None` | Valores antes e depois |
| `justificativa` | só em `DELETE` | `None` | Motivo da exclusão |

O IP vem de `X-Forwarded-For` (se houver) ou do `remote_addr`.

## Leitura sensível: `@acesso_auditado`

```
@acesso_auditado("prontuario", operacao="leitura")
def ver(...):
    return resposta, {"uuid_paciente": ...}
```

1. A view executa e devolve a resposta (ou `(resposta, detalhes)`).
2. Só **depois do sucesso** o log de acesso é gravado e confirmado. Se a view levantar exceção, nenhum log de acesso é criado por este decorator.
3. Se a gravação do log falhar, há `rollback` e a exceção segue adiante; a resposta não é entregue.

`operacao` é obrigatória e precisa estar entre `leitura`, `escrita`, `exclusao-logica` e `exportacao`, validada quando a rota é declarada.

| Chave de `detalhes` | Padrão | Significado |
|---|---|---|
| `recurso_acessado` | `recurso` do decorator | Recurso efetivamente acessado |
| `operacao` | `operacao` do decorator | Sobrescreve a categoria |
| `resultado` | `"sucesso"` | Resultado do acesso |
| `uuid_paciente` | `None` | Paciente cujos dados foram lidos |

Acessos negados têm um método próprio no service, `registrar_acesso_negado`, que grava `resultado="acesso-negado"` e o `motivo_negacao`.

---

# Consulta

## Período: janela de 7 dias

As telas de auditoria consultam no máximo 7 dias por vez. A regra é aplicada em `/acessos`, `/alteracoes` (listagem) e `/profissionais/<uuid>/detalhe`:

| Situação | Resultado |
|---|---|
| Só `data_inicio` | `data_fim` = `data_inicio` + 7 dias |
| Só `data_fim` | `data_inicio` = `data_fim` - 7 dias |
| As duas, intervalo de até 7 dias | Usadas como vieram |
| As duas, intervalo maior que 7 dias | Erro: "Periodo maximo de consulta e 7 dias" |
| As duas, `data_fim` antes de `data_inicio` | Erro: "data_fim nao pode ser anterior a data_inicio" |
| Nenhuma | Últimos 7 dias (`data_fim` = agora em UTC, `data_inicio` = `data_fim` - 7 dias) |

O resumo por profissional não recebe datas. O drill-down por registro (`tabela` + `uuid_registro`) também ignora o período.

## Paginação

| Estilo | Usado em | Como funciona |
|---|---|---|
| Offset/limit | `/profissionais/resumo`, `/acessos`, `/alteracoes` | `page` (mínimo 1) e `limit`. Padrão 10; máximo 50; valor vazio ou não positivo volta ao padrão |
| Cursor por data (keyset) | `/profissionais/<uuid>/detalhe` | Páginas ancoradas no último item visto, estáveis mesmo com logs novos chegando |

### Como o cursor funciona

Com offset, a página é definida pela posição; se chegam logs novos entre uma chamada e outra, itens deslocam e podem ser pulados ou repetidos. O cursor ancora no próprio valor do último item.

1. Primeira chamada sem cursor: devolve os `limit` itens mais recentes de cada bloco (acessos e alterações).
2. A resposta traz `tem_mais` e `proximo_cursor` (`cursor_data` + `cursor_uuid` do último item) em cada bloco.
3. Para carregar mais, o front reenvia esse par como `cursor_acessos_data`/`cursor_acessos_uuid` ou `cursor_alteracoes_data`/`cursor_alteracoes_uuid`.
4. O repository filtra pela tupla `(data, uuid) < (cursor_data, cursor_uuid)`. O `uuid` desempata logs no mesmo instante, evitando perda ou repetição.
5. Os blocos paginam de forma independente: carregar mais acessos não move o cursor das alterações.

O repository pede um item a mais que o `limit` só para saber se existe próxima página, sem contar todos os registros.

## Resumo por profissional

A tela principal lista profissionais em ordem alfabética, cada um com o último acesso e a última alteração. É uma única query partindo de `Usuario`, com `EXISTS` para "tem ao menos um log de acesso ou de alteração". Paginar os dois logs separados e juntar depois quebraria a ordenação global e o "N por página"; `EXISTS` (em vez de `JOIN`/`UNION`) evita duplicar quem tem os dois tipos de log.

O "último evento" é buscado apenas para os profissionais da página atual.

Filtros independentes e combináveis:

| Filtro | Efeito |
|---|---|
| `nome` | Contém, sem distinguir maiúsculas |
| `funcao_clinica` | `medico` ou `enfermeiro`, via papel profissional ativo |
| `is_admin` | `true`/`false` em `Usuario.is_admin` |
| `acao` | Texto livre em `LogAlteracao.acao`, categoria em `LogAcesso.operacao`, ou operação SQL traduzida |

Exemplo: `funcao_clinica=medico` com `is_admin=true` devolve só administradores que também são médicos.

## Filtro `acao` (resumo e detalhe)

O parâmetro `acao` tem o mesmo significado no resumo e no detalhe do profissional:

| Log | O que `acao` compara |
|---|---|
| Alterações | `LogAlteracao.acao` (texto livre, ex.: `editar_paciente`) **ou** a operação SQL traduzida da categoria (ex.: `escrita` = `INSERT`/`UPDATE`) |
| Acessos | `LogAcesso.operacao` (categoria). No detalhe, `operacao_acesso`, se informado, tem precedência |

`LogAcesso` não tem campo de ação em texto livre. Por isso uma ação como `editar_paciente` só retorna itens no bloco de alterações, enquanto uma categoria como `escrita` retorna itens nos dois blocos.