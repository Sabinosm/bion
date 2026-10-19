# Controllers de Configurações

Rotas HTTP do domínio de configurações do usuário (`controller.py`, blueprint `configuracao`). O prefixo real do blueprint é `/v1/api/configuracoes`; os caminhos abaixo são relativos a ele.

Para as regras de negócio (cascata de liberação, padrão pessoal e institucional, merge de configurações), ver `configuracao_fluxo.md`.

---

# Convenções gerais

## Exigência de sessão

| Marcador | Significa |
|---|---|
| Sessão completa | Usuário autenticado e sem pendências (`@requer_login`) |
| Papel clínico | Sessão completa com função de médico ou enfermeiro (`@requer_papel_clinico("medico", "enfermeiro")`) |

Todas as rotas atuam sobre o **usuário da sessão**: não existe parâmetro para consultar ou alterar a configuração de outra pessoa.

## Formato das respostas

Todas usam o envelope padrão `json_success(data=..., message=...)`.

## Identificação de protocolos

Os protocolos são identificados pelo **UUID do catálogo** (o mesmo que a página de catálogo usa), nunca pelo id numérico.

## Escopos

`escopo` aceita `triagem`, `consulta` ou `ambos`.

## Corpo JSON

As rotas com corpo esperam um objeto JSON. Corpo ausente equivale a objeto vazio; qualquer outro formato (lista, texto, número) é recusado como dados inválidos.

---

# Configurações do usuário

## `GET /`

Configurações do usuário logado. Na primeira vez são criadas com os padrões. **Sessão completa.**

**Resposta (200):** dentro de `data`: `configuracoes`.

```json
{
  "configuracoes": {
    "design": { "tema": "light", "tamanho_fonte": "medio" },
    "preferencias": { "linguagem": ["pt-BR"] }
  }
}
```

## `PUT /`

Atualiza as configurações por merge parcial por seção. **Sessão completa.**

| Campo (JSON) | Obrigatório | Descrição |
|---|---|---|
| `configuracoes` | sim | Objeto com qualquer subconjunto de `design` e `preferencias` |
| `configuracoes.design.tema` | não | `dark`, `light`, `blue`, `blue-light`, `burgundy`, `burgundy-light`, `teal`, `teal-light` |
| `configuracoes.design.tamanho_fonte` | não | `pequeno`, `medio`, `grande` |
| `configuracoes.preferencias.linguagem` | não | Lista não vazia com `pt-BR` e/ou `en-US`; substitui a lista atual |

**Resposta (200):** `configuracoes` completas após o merge; mensagem "Configurações atualizadas."

---

# Protocolos

Todas exigem **Papel clínico**.

## `GET /protocolos/default`

Protocolo que a consulta carrega por padrão para um escopo.

| Parâmetro (query) | Obrigatório | Descrição |
|---|---|---|
| `escopo` | sim | `triagem`, `consulta` ou `ambos` |

**Resposta (200):** dentro de `data`:

| Campo | Descrição |
|---|---|
| `protocolo` | `uuid`, `nome_protocolo`, `sigla`, `escopo_uso` |
| `origem` | `pessoal`, `institucional` ou `primeiro_liberado` |

## `GET /protocolos`

Lista as preferências de protocolo do usuário, só dos protocolos que a empresa mantém liberados. Cada item traz `uuid`, `sigla`, `em_uso` e `escopo_default`, o que a página de catálogo cruza com os cards para pintar a estrela.

**Resposta (200):** `data` é a lista de itens.

## `PUT /protocolos/<uuid_protocolo>/habilitar`

Habilita o protocolo para o usuário. Só vale para protocolos liberados pela instituição. Sem corpo.

| Parâmetro | Local | Descrição |
|---|---|---|
| `uuid_protocolo` | caminho | UUID do protocolo no catálogo |

**Resposta (200):** o item atualizado; mensagem "Protocolo habilitado."

## `PUT /protocolos/<uuid_protocolo>/desabilitar`

Desabilita o protocolo e libera o seu padrão pessoal. Não é permitido para protocolo obrigatório nem para o padrão da instituição. Sem corpo.

| Parâmetro | Local | Descrição |
|---|---|---|
| `uuid_protocolo` | caminho | UUID do protocolo no catálogo |

**Resposta (200):** o item atualizado; mensagem "Protocolo desabilitado."

## `PUT /protocolos/<uuid_protocolo>/default`

Define o protocolo como padrão pessoal de um escopo. O protocolo precisa estar em uso, liberado pela instituição e servir ao escopo. Se outro protocolo era o padrão do escopo, ele é liberado na mesma operação.

| Parâmetro | Local | Obrigatório | Descrição |
|---|---|---|---|
| `uuid_protocolo` | caminho | sim | UUID do protocolo no catálogo |
| `escopo` | corpo (JSON) | sim | `triagem`, `consulta` ou `ambos` |

**Resposta (200):** o item atualizado; mensagem "Protocolo definido como padrão."

## `DELETE /protocolos/<uuid_protocolo>/default`

Remove o padrão pessoal do protocolo sem desabilitá-lo; o escopo volta a seguir o padrão da instituição. Sem corpo.

| Parâmetro | Local | Descrição |
|---|---|---|
| `uuid_protocolo` | caminho | UUID do protocolo no catálogo |

**Resposta (200):** o item atualizado; mensagem "Padrão pessoal removido; vale o padrão da instituição."

---

# Resumo das rotas

| Método | Rota | Sessão exigida | Retorno |
|---|---|---|---|
| GET | `/` | Sessão completa | Configurações do usuário |
| PUT | `/` | Sessão completa | Configurações após o merge |
| GET | `/protocolos/default` | Papel clínico | Protocolo padrão do escopo e origem |
| GET | `/protocolos` | Papel clínico | Preferências de protocolo do usuário |
| PUT | `/protocolos/<uuid_protocolo>/habilitar` | Papel clínico | Item atualizado |
| PUT | `/protocolos/<uuid_protocolo>/desabilitar` | Papel clínico | Item atualizado |
| PUT | `/protocolos/<uuid_protocolo>/default` | Papel clínico | Item atualizado |
| DELETE | `/protocolos/<uuid_protocolo>/default` | Papel clínico | Item atualizado |
