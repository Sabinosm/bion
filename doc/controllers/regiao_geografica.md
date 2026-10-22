# Controllers de Regiões Geográficas

Rotas HTTP do domínio de regiões geográficas (`controller.py`, blueprint `regiao`). O prefixo das URLs depende de como o blueprint é registrado na aplicação; os caminhos abaixo são relativos a ele.

Para o funcionamento interno (criação automática de município, fontes externas, cache de CEP), ver `regiao_fluxo.md`.

---

# Convenções gerais

## Exigência de sessão

Todas as rotas exigem **sessão completa** (`@requer_login`). Não há restrição por papel: qualquer usuário autenticado pode consultar.

## Formato das respostas

| Rota | Formato |
|---|---|
| `GET /`, `GET /uuid/<uuid>`, `GET /codigo/<codigo_ibge>` | Envelope padrão `json_success(data=...)` |
| `GET /cep/<cep>` | O objeto da região direto, sem o envelope `data` |

Cada região é serializada por `to_dict()`.

---

# Rotas

## `GET /`

Lista as regiões em ordem alfabética, paginadas de 15 em 15, todas ou só as de um tipo.

| Parâmetro (query) | Obrigatório | Padrão | Descrição |
|---|---|---|---|
| `tipo` | não | todos | Código do tipo de jurisdição, ex.: `municipio`, `estado` |
| `page` | não | 1 | Número da página, a partir de 1 |
| `limit` | não | 15 | Itens por página; máximo 50 |

**Resposta (200):** dentro de `data`:

```json
{
  "itens": [],
  "paginacao": { "total": 0, "page": 1, "limit": 15 }
}
```

`total` é a contagem de todas as regiões do filtro, e não só as da página.

## `GET /uuid/<uuid>`

Detalhes de uma região pelo UUID.

| Parâmetro | Local | Descrição |
|---|---|---|
| `uuid` | caminho | UUID da região |

**Resposta (200):** `data` é a região.

## `GET /codigo/<codigo_ibge>`

Detalhes de uma região pelo código IBGE do município. Se o código não existir no banco, a rota o confirma na API do IBGE e **cadastra a região automaticamente** antes de responder.

| Parâmetro | Local | Descrição |
|---|---|---|
| `codigo_ibge` | caminho | Código IBGE do município, 7 dígitos |

**Resposta (200):** `data` é a região (já existente ou recém-criada).

O código precisa ter exatamente 7 dígitos; fora do formato, a rota o recusa como dados inválidos. Um código válido que não exista no IBGE não gera região.

## `GET /cep/<cep>`

Região (município) correspondente ao CEP. O CEP é resolvido em código IBGE e a região é devolvida, sendo cadastrada automaticamente se ainda não existir.

| Parâmetro | Local | Descrição |
|---|---|---|
| `cep` | caminho | CEP com 8 dígitos, com ou sem hífen; fora do formato, a rota o recusa como dados inválidos |

**Resposta (200):** o objeto da região, sem envelope.

---

# Resumo das rotas

| Método | Rota | Sessão exigida | Parâmetros | Retorno |
|---|---|---|---|---|
| GET | `/` | Sessão completa | `tipo`, `page`, `limit` (query, opcionais) | Página de regiões (15 por padrão) |
| GET | `/uuid/<uuid>` | Sessão completa | `uuid` | Região |
| GET | `/codigo/<codigo_ibge>` | Sessão completa | `codigo_ibge` | Região (criada se necessário) |
| GET | `/cep/<cep>` | Sessão completa | `cep` | Região, sem envelope (criada se necessário) |