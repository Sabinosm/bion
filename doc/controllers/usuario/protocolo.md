# Protocolo — Controllers

Todas as rotas do domínio são registradas no blueprint `bp_protocolo` (definido em `protocolo_catalogo_controller.py`). Os caminhos abaixo são relativos ao prefixo com que esse blueprint é registrado na aplicação.

Respostas seguem o padrão do projeto: `json_success(data, message, status)` em caso de sucesso e `json_error(mensagem, status)` em caso de erro. Exceções `BionException` são convertidas em `json_error` com a mensagem e o `status_code` da própria exceção.

## Erros

| Exceção | Status | Quando |
|---|---|---|
| `RecursoNaoEncontradoError` | 404 | Protocolo, versão vigente, configuração ou composição inexistente |
| `DadosInvalidosError` | 422 | Corpo inválido, respostas inválidas ou protocolo de outro tipo na rota |
| `ConflictoError` | 409 | Protocolo não liberado pela instituição, inativo no catálogo ou já executado para o input |
| `EstruturaInvalida`, `AgregacaoInvalida`, `GatilhoInvalido`, `CondicaoInvalida` | 500 | Configuração cadastrada do protocolo inconsistente |

As quatro exceções de configuração herdam de `ConfiguracaoProtocoloInvalidaError`. O usuário recebe uma mensagem própria de cada uma ("... Contate o suporte."); o detalhe técnico fica no atributo `detalhe` e é registrado no log com nível `error`. Elas também são `ValueError`, então o seed e os testes que capturam `ValueError` continuam funcionando.

## Resumo das rotas

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| GET | `/` | Logado | Lista todos os protocolos cadastrados |
| GET | `/catalogo` | Logado | Resumos do catálogo ativo, com status de liberação da empresa |
| GET | `/catalogo/filtrar` | Logado | Mesmo resumo, com filtros e paginação |
| GET | `/catalogo/<uuid_protocolo>` | Logado | Detalhe do protocolo + resumo + versão ativa |
| GET | `/news2/<uuid_protocolo>/campos` | Logado | Campos exigidos pelo NEWS2 |
| POST | `/news2/<uuid_protocolo>/executar` | Médico ou enfermeiro | Executa o NEWS2 e registra o resultado |
| GET | `/protocolo-composto/<uuid_protocolo>/campos` | Logado | Campos exigidos pelo protocolo composto |
| GET | `/protocolo-composto/<uuid_protocolo>/composicao` | Logado | Estrutura da composição (somente leitura) |
| POST | `/protocolo-composto/<uuid_protocolo>/executar` | Médico ou enfermeiro | Executa o protocolo composto e registra o resultado |

"Logado" = `@requer_login`. "Médico ou enfermeiro" = `@requer_papel_clinico("medico", "enfermeiro")`.

As rotas de `/news2` e `/protocolo-composto` só aceitam protocolos do tipo da própria família (`escore-ponderado` e `protocolo-composto`); com o UUID de um protocolo de outro tipo, respondem com erro de dados inválidos.

A empresa e o usuário da sessão vêm de `get_id_empresa_sessao()` e `get_id_usuario_sessao()`; nenhuma rota recebe empresa ou executor no corpo.

---

## `protocolo_catalogo_controller.py`

### `GET /`

Lista todos os protocolos cadastrados, sem filtro de status ou empresa.

- **Resposta:** lista de protocolos (`to_dict()` de cada um).

### `GET /catalogo`

Página de catálogo sem filtro. Lista os protocolos com `status = 'ativo'` e, para cada um, o status de liberação da empresa do usuário.

- **Resposta:** lista de resumos (ver "Resumo do card" em `protocolo.md`).

### `GET /catalogo/filtrar`

Página de catálogo com filtros e paginação.

| Parâmetro (query) | Tipo | Padrão | Descrição |
|---|---|---|---|
| `tipo_protocolo` | texto | — | Ex.: `escore-ponderado` |
| `escopo_populacao` | texto | — | Ex.: `adulto` |
| `escopo_uso` | texto | — | Casa o valor informado ou `ambos` |
| `apenas_liberados` | texto | `false` | Só vale `true` (exato) para filtrar liberados |
| `pagina` | inteiro | `0` | Página de 20 itens, ordenados por ID (negativo vale 0) |

- **Resposta:** lista de resumos, no máximo 20 por página.

### `GET /catalogo/<uuid_protocolo>`

Detalhe do protocolo. Aberto a qualquer logado: estudar um protocolo não é usá-lo.

- **Resposta:** `{ "protocolo": {...}, "resumo": {...}, "versao_ativa": {...} | null }`.
- **Erros:** protocolo inexistente (`RecursoNaoEncontradoError`).

---

## `news2/protocolo_escore_config_controller.py`

### `GET /news2/<uuid_protocolo>/campos`

Campos que o protocolo exige, para estudo. Sem gate de liberação.

- **Resposta:** lista de `{ "campo", "texto", "tipo_campo", "opcoes" }`.
  - `tipo_campo`: `numero` ou `enum`.
  - `opcoes`: lista de `{ "valor", "rotulo" }` para `enum`; `null` para `numero`.
- **Erros:** UUID inexistente ou protocolo sem configuração NEWS2 (`RecursoNaoEncontradoError`); protocolo de outro tipo (`DadosInvalidosError`).

### `POST /news2/<uuid_protocolo>/executar`

Valida a liberação da empresa, calcula e persiste a execução.

- **Corpo** (validado por `SchemaExecucaoRequest`):

| Campo | Tipo | Descrição |
|---|---|---|
| `id_input` | inteiro maior que zero | Input de atendimento sobre o qual o protocolo é executado |
| `respostas` | objeto | Código do campo → valor (texto, número, booleano ou `null` para ausente). Opcional, vazio por padrão |

```json
{
  "id_input": 123,
  "respostas": { "freq_respiratoria": 18, "nivel_consciencia": "alerta" }
}
```

- **Sucesso:** status `201`, mensagem "Protocolo executado e registrado.", `data` = execução gravada.
- **Erros:**
  - Corpo inválido (`id_input` ausente ou inválido, `respostas` com tipo errado): `DadosInvalidosError` listando os problemas.
  - Protocolo de outro tipo: `DadosInvalidosError`.
  - Protocolo não liberado pela empresa, inativo no catálogo ou já executado para o input: `ConflictoError`.
  - Protocolo ou versão vigente inexistente: `RecursoNaoEncontradoError`.
  - Respostas inválidas (campo desconhecido, número inválido ou fora das faixas, opção inexistente): `DadosInvalidosError`.

---

## `protocolo_composto/protocolo_composto_controller.py`

### `GET /protocolo-composto/<uuid_protocolo>/campos`

União das variáveis de todos os módulos. Sem gate de liberação.

- **Resposta:** lista de `{ "campo", "texto", "tipo_campo", "opcoes" }`.
  - `tipo_campo`: `numero`, `enum` ou `booleano`.
  - `opcoes`: lista de `{ "valor", "rotulo" }` para `enum`; `null` nos demais.
- **Erros:** UUID inexistente, protocolo sem versão vigente ou sem composição (`RecursoNaoEncontradoError`); protocolo de outro tipo (`DadosInvalidosError`).

### `GET /protocolo-composto/<uuid_protocolo>/composicao`

Estrutura do composto para a página de detalhe. Não expõe a configuração interna dos módulos.

- **Resposta:**

| Campo | Conteúdo |
|---|---|
| `versao` | `numero_versao`, `vigente_desde` |
| `agregacao` | Tipo de agregação (`nenhuma` se não houver configuração) |
| `regra_gatilho` | Regra de gatilho do protocolo ou `null` |
| `modulos` | Lista, na ordem da composição |

  Cada item de `modulos`: `papel`, `grupo_agregacao`, `ordem`, `modulo` (`uuid`, `nome_modulo`, `sigla`, `tipo_modulo`, `familia_calculo`, `tipo_saida`, `descricao`, `referencia_bibliografica`), `numero_versao`, `explicacao` e `campos` (`codigo`, `nome`, `tipo_dado`, `unidade`, `opcoes`, `valor_min`, `valor_max`, `obrigatorio`, `ordem`).

- **Erros:** UUID inexistente, sem versão vigente ou sem composição (`RecursoNaoEncontradoError`); protocolo de outro tipo (`DadosInvalidosError`).

### `POST /protocolo-composto/<uuid_protocolo>/executar`

Valida a liberação da empresa, calcula e persiste a execução.

- **Corpo:** mesmo formato do NEWS2 (`SchemaExecucaoRequest`).

```json
{
  "id_input": 123,
  "respostas": { "idade": 67, "fumante": true, "sexo_biologico": "F" }
}
```

  Tipos esperados: número para `numero`, uma das opções para `enum` e `true`/`false` para `booleano`. Variável não enviada, `null` ou texto vazio é tratada como dado ausente.

- **Sucesso:** status `201`, mensagem "Protocolo executado e registrado.", `data` = execução gravada (com o `SchemaResultado` em `resultado_calculado_json`).
- **Erros:** os mesmos da execução do NEWS2.

---

## Permissões

| Ação | Quem pode |
|---|---|
| Listar catálogo, ver detalhe, campos e composição | Qualquer usuário logado, com o protocolo liberado ou não |
| Executar protocolo | Médico ou enfermeiro, e somente se a empresa liberou o protocolo (`empresa_protocolo.ativo`) |

A preferência pessoal (favorito/padrão) nunca bloqueia a execução.
