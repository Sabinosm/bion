# Controllers: Empresa e Liberação de Protocolos

Documentação das rotas JSON dos domínios **Empresa** (tenant) e **EmpresaProtocolo** (liberação institucional de protocolos). Para o raciocínio por trás das regras e o passo a passo dos processos, ver `empresa_fluxo.md`.

---

# Convenções

## Prefixos

| Domínio | Blueprint | Prefixo |
|---|---|---|
| Empresa | `empresa` | definido no `main.py` (o código se refere a esta rota como `/empresas/`) |
| EmpresaProtocolo | `empresa_protocolo` | `/v1/api/liberacao-protocolos` |

Os caminhos abaixo são relativos ao prefixo de cada domínio.

## Perfis de acesso

| Marca na tabela | Significado |
|---|---|
| Pública | Sem autenticação |
| Admin | Exige `@requer_admin` |
| Super admin | Exige `@requer_super_admin` (o admin fundador, criado junto com a empresa) |

## Formato das respostas

- Sucesso: `json_success`, com `data` e, quando há, `message`. Criação responde com status `201`; as demais, `200`.
- Erro: `json_error(message, status_code)`. O status HTTP é o definido em cada exceção de `src.core.exceptions` (`DadosInvalidosError`, `ConflictoError`, `RecursoNaoEncontradoError`, `BionException`). Erros de validação por campo vêm em `erros`.

## Auditoria

Rotas marcadas com `@acao_sensivel` registram a ação na auditoria. A rota devolve, junto com a resposta, os metadados do registro:

| Metadado | Conteúdo |
|---|---|
| `id_registro` | Id do registro afetado |
| `uuid_registro` | Uuid do registro, quando aplicável |
| `operacao` | `UPDATE` em caso de sucesso; `NOOP` quando a tentativa falha |

Tentativas que falham também são registradas (como `NOOP`).

---

# Empresa

## Resumo das rotas

| Método | Rota | Acesso | Auditada | Função |
|---|---|---|---|---|
| GET | `/` | Admin | Não | Dados da empresa da sessão |
| PUT | `/` | Super admin | Sim (`atualizar_empresa`) | Atualiza dados autogerenciáveis |
| POST | `/create` | Pública | Não | Cadastra empresa + admin fundador |
| GET | `/existe-cnpj/<cnpj>` | Pública | Não | Verifica se o CNPJ já está cadastrado |
| GET | `/existe-cnes/<cnes>` | Pública | Não | Verifica se o CNES já está cadastrado |

## GET `/`

Retorna os dados da empresa da sessão (a empresa é identificada pela sessão, não por parâmetro).

| Item | Detalhe |
|---|---|
| Sucesso | `200` com `data` = dados da empresa |
| Erros | `RecursoNaoEncontradoError` se a empresa não existir |

## PUT `/`

Atualiza os campos autogerenciáveis da empresa da sessão. Atualização **parcial**: campos ausentes não são alterados.

**Body (JSON)**

| Campo | Tipo | Regra |
|---|---|---|
| `nome_fantasia` | string | 2 a 255 caracteres |
| `cnes` | string | 7 dígitos (caracteres não numéricos são removidos antes); vazio = sem mudança; não pode pertencer a outra empresa |
| `numero` | string | Até 10 caracteres: letras, números, `°`, `º`, `ª`, espaço, `-`, `/`, `.`, `,` |
| `bairro` | string | Até 100 caracteres |
| `complemento` | string | Até 150 caracteres |
| `cep` | string | CEP válido; gravado só com dígitos; se mudar, a região geográfica é recalculada |
| `dpo_nome` | string | Até 255 caracteres; vazio ou `null` = volta ao nome do super admin |
| `dpo_email` | string | E-mail válido, até 255 caracteres; vazio ou `null` = volta ao e-mail do super admin |
| `endereco` | objeto | Opcional. Formato `{cep, bairro, numero, complemento}` (o mesmo do retorno da empresa); é achatado nos campos acima. Se o mesmo campo vier plano e aninhado, vale o plano |

Qualquer outro campo é rejeitado (inclui `cnpj`, `status_plano` e `plano`, que não podem ser alterados por esta rota).

| Item | Detalhe |
|---|---|
| Sucesso | `200`, `data` = empresa atualizada, `message` = "Empresa atualizada." |
| Auditoria | `UPDATE` com `id_registro` e `uuid_registro` da empresa; em falha, `NOOP` com `id_registro = null` e o uuid da empresa da sessão |
| Erros | `RecursoNaoEncontradoError` (empresa inexistente), `DadosInvalidosError` (payload inválido ou CEP sem região), `ConflictoError` (CNES de outra empresa), `BionException` (uuid da sessão não bate com a empresa) |

O service é chamado com `commit=False`: grava com `flush`, sem commit próprio.

## POST `/create`

Cadastra a empresa e o admin fundador numa **única transação**. Rota pública.

**Body (JSON)**: `{"empresa": {...}, "admin": {...}}`

Campos de `empresa`:

| Campo | Tipo | Regra |
|---|---|---|
| `nome_fantasia` | string | **Obrigatório**, 2 a 255 caracteres |
| `razao_social` | string | Até 255 caracteres |
| `cnpj` | string | CNPJ válido; gravado só com dígitos |
| `cnes` | string | 7 dígitos |
| `numero` | string | Até 10 caracteres (mesma regra do PUT) |
| `bairro` | string | Até 100 caracteres |
| `complemento` | string | Até 150 caracteres |
| `cep` | string | CEP válido; define a região geográfica |
| `status_plano` | string | `ativo` (padrão), `inativo`, `suspenso` ou `cancelado` |
| `plano` | string | Livre |
| `dpo_nome` | string | Até 255; vazio = nome do admin criado |
| `dpo_email` | string | E-mail válido, até 255; vazio = e-mail do admin criado |

É obrigatório informar **CNPJ ou CNES** (ao menos um). Campos desconhecidos são rejeitados.

Campos de `admin`: validados pelo domínio Usuário. A rota força `is_admin = true` e o usuário é criado como **super admin** da empresa.

| Item | Detalhe |
|---|---|
| Sucesso | `201`, `data` = `{"empresa": {...}, "admin": {...}}`, `message` = "Empresa e admin criados com sucesso." |
| Erros | `DadosInvalidosError` (com `erros` por campo; erros gerais do schema, como faltar CNPJ e CNES, ficam associados ao campo `cnpj`), `ConflictoError` (CNPJ ou CNES já cadastrado) |
| Atomicidade | Se a criação da empresa ou do admin falhar, nada é gravado |

## GET `/existe-cnpj/<cnpj>` e GET `/existe-cnes/<cnes>`

Informam se o identificador já está em uso. Rotas públicas.

| Item | Detalhe |
|---|---|
| Parâmetro | Somente dígitos, sem máscara. Qualquer outro caractere é bloqueado |
| Sucesso | `200`, `data` = `{"existe": true | false}` |
| Erros | `DadosInvalidosError` se o valor tiver caracteres que não sejam dígitos |

---

# EmpresaProtocolo (liberação institucional)

Todas as rotas identificam o protocolo pelo **uuid do catálogo** (o mesmo usado pela página de catálogo). O id numérico só circula internamente e no registro de auditoria.

## Resumo das rotas

| Método | Rota | Acesso | Auditada | Função |
|---|---|---|---|---|
| GET | `/` | Admin | Não | Estado de todos os protocolos do catálogo para a empresa |
| PUT | `/<uuid_protocolo>/status` | Super admin | Sim (`alterar_status_protocolo`) | Libera/bloqueia o protocolo e/ou muda a política |
| PUT | `/<uuid_protocolo>/default` | Super admin | Sim (`definir_default_institucional`) | Define o padrão institucional de um escopo |

## GET `/`

Lista **todos** os protocolos do catálogo cruzados com os vínculos da empresa da sessão. Protocolo que a empresa nunca tocou aparece como não liberado.

**Item da resposta**

| Campo | Conteúdo |
|---|---|
| `protocolo` | Dados do protocolo do catálogo |
| `ativo` | `true` se liberado; `false` se bloqueado ou nunca tocado |
| `politica` | `obrigatorio` ou `opcional`; `null` se nunca tocado |
| `escopo_default_institucional` | Escopo em que é o padrão (`triagem`, `consulta` ou `ambos`); `null` se não é padrão ou nunca tocado |

## PUT `/<uuid_protocolo>/status`

Libera ou bloqueia o protocolo para a empresa e, opcionalmente, altera a política.

**Body (JSON)**

| Campo | Tipo | Regra |
|---|---|---|
| `ativo` | bool | **Obrigatório** |
| `politica` | string | Opcional: `obrigatorio` ou `opcional`. Omitida = mantém a atual |

Campos desconhecidos são rejeitados. Quem aprovou (`aprovado_por`) e quando (`aprovado_em`) vêm da sessão, nunca do body.

| Item | Detalhe |
|---|---|
| Sucesso | `200`, `data` = vínculo + `uuid_protocolo`, `message` = "Status do protocolo atualizado." |
| Auditoria | `id_registro` = id do protocolo no catálogo; `uuid_registro` = `null`; `UPDATE` em sucesso, `NOOP` em falha (com o id, se o protocolo existe) |
| Erros | `RecursoNaoEncontradoError` (uuid inexistente), `DadosInvalidosError` (body inválido; desativar protocolo obrigatório), `ConflictoError` (desativar o padrão institucional; ficar com menos de 2 ativos; operação simultânea) |

Para desativar um protocolo obrigatório, envie `"politica": "opcional"` junto com `"ativo": false`.

## PUT `/<uuid_protocolo>/default`

Define o protocolo como padrão institucional de um escopo.

**Body (JSON)**

| Campo | Tipo | Regra |
|---|---|---|
| `escopo` | string | **Obrigatório**: `triagem`, `consulta` ou `ambos` |

| Item | Detalhe |
|---|---|
| Sucesso | `200`, `data` = vínculo + `uuid_protocolo`, `message` = "Protocolo padrão institucional definido." |
| Auditoria | Igual à rota de status |
| Erros | `RecursoNaoEncontradoError` (uuid inexistente), `DadosInvalidosError` (body inválido; protocolo não ativo para a empresa; protocolo não serve ao escopo), `ConflictoError` (protocolo já é padrão de outro escopo; operação simultânea) |