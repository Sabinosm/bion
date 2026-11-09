# Fluxo de Configurações do Usuário

Documentação das preferências por usuário no Bion: aparência e idioma da interface e os protocolos clínicos que cada profissional habilita e define como padrão, sempre dentro do que a instituição liberou.

---

# Contexto e conceitos

## Visão geral

Cada usuário tem uma **configuração** própria, composta por duas partes independentes:

| Parte | O que guarda | Onde vive | Quem pode mexer |
|---|---|---|---|
| Aparência e idioma | Tema, tamanho da fonte, idiomas | Um JSON na configuração do usuário | Qualquer usuário logado |
| Protocolos | Quais protocolos o usuário usa e qual é o padrão de cada escopo | Uma linha por protocolo, ligada à configuração | Médico e enfermeiro, dentro do que a instituição liberou |

Os protocolos (MTS, NEWS2, compostos) **não ficam no JSON**: cada protocolo habilitado vira uma linha própria. Isso permite restringir por instituição e garantir unicidade do padrão por escopo no banco.

## Camadas e arquivos

| Arquivo | Responsabilidade |
|---|---|
| `controller.py` | Rotas HTTP, leitura do corpo e da querystring, formato da resposta |
| `service.py` | Regras de negócio: merge de configurações, cascata de liberação, cadeia de padrão |
| `repository.py` | Consultas e gravações; trata conflito de concorrência |
| `schema_config.py` | Validação do payload de configurações |

## Criação sob demanda

A configuração **não é criada no cadastro do usuário**: nasce no primeiro uso (ao abrir as configurações, ao carregar `/me`, ou ao mexer em protocolos). Na criação:

1. A configuração recebe os padrões de aparência e idioma.
2. Os protocolos que a instituição marcou como **padrão institucional** entram automaticamente como favoritos do usuário (`em_uso = true`), sem definir padrão pessoal.

Não definir o padrão pessoal na semeadura é deliberado: a cadeia de fallback continua viva, e uma mudança futura do padrão da instituição vale para quem nunca escolheu o seu.

Usuário sem configuração é tratado como exceção a corrigir: recebe os padrões na hora, em vez de falhar. A criação é **tudo ou nada**: a configuração e os favoritos entram na mesma transação, então nunca sobra uma configuração sem os favoritos (que, existindo, não seria semeada de novo). Se algo falhar, nada é gravado e a próxima requisição tenta de novo.

### Padrões iniciais

| Seção | Campo | Valor inicial |
|---|---|---|
| `design` | `tema` | `light` |
| `design` | `tamanho_fonte` | `medio` |
| `preferencias` | `linguagem` | `["pt-BR"]` |

---

# Aparência e idioma

## Valores permitidos

O payload é validado por um schema que espelha as opções do frontend (`settingsModal.html`). O que não for uma dessas opções é recusado.

| Campo | Valores aceitos |
|---|---|
| `design.tema` | `dark`, `light`, `blue`, `blue-light`, `burgundy`, `burgundy-light`, `teal`, `teal-light` |
| `design.tamanho_fonte` | `pequeno`, `medio`, `grande` |
| `preferencias.linguagem` | Lista não vazia com `pt-BR` e/ou `en-US` |

Seções ou campos desconhecidos (ex.: `designe`) também são rejeitados, para um erro de digitação não ser salvo em silêncio.

## Atualização por merge parcial

O usuário pode enviar só o que quer mudar. O merge é **por seção**:

| Envio | Resultado |
|---|---|
| `{"design": {"tema": "dark"}}` | Troca só o tema; `tamanho_fonte` e `preferencias` ficam como estavam |
| `{"preferencias": {"linguagem": ["en-US"]}}` | Substitui a lista de idiomas por completo |
| `{}` | Nada muda |

Listas são substituídas por inteiro, e não mescladas, porque representam uma seleção. Campos enviados como `null` são ignorados, e não apagam o valor existente.

---

# Protocolos

## Cascata de restrição institucional

O profissional só trabalha com o que a instituição permitiu. A liberação vive no vínculo entre empresa e protocolo:

| Atributo do vínculo | Efeito sobre o usuário |
|---|---|
| `ativo` | Só protocolos liberados (`ativo = true`) podem ser habilitados ou virar padrão |
| `politica = obrigatorio` | O protocolo não pode ser desabilitado pelo usuário |
| `escopo_default_institucional` | Define o padrão da instituição para aquele escopo; esse protocolo também não pode ser desabilitado |

O **catálogo efetivo** do usuário é: liberado pela empresa **e** em uso.

A listagem de preferências do usuário mostra apenas protocolos que a empresa mantém liberados. Se a empresa desativar um depois, ele some da lista; a linha do usuário é preservada e volta a aparecer se a empresa o liberar de novo.

## Estado pessoal de um protocolo

Cada linha de preferência guarda:

| Campo | Significado |
|---|---|
| `em_uso` | O protocolo está habilitado (favorito) para este usuário |
| `escopo_default` | Escopo em que este é o padrão **pessoal** (`triagem`, `consulta` ou `ambos`), ou vazio |

Regras:

- O padrão pessoal só existe para protocolo **em uso**. Ao desabilitar, o padrão é liberado automaticamente.
- Cada escopo tem no máximo **um** padrão pessoal por usuário, garantido por restrição de unicidade no banco.
- Um protocolo só serve como padrão de um escopo se o seu uso permitir: um de triagem não vira padrão de consulta, e o escopo `ambos` só vale para protocolos de uso `ambos`.

## Escopos

| Escopo | Significa |
|---|---|
| `triagem` | Atendimento de triagem |
| `consulta` | Consulta |
| `ambos` | Serve às duas; um protocolo `ambos` é fallback tanto de triagem quanto de consulta |

## Fluxos

### Habilitar

1. O protocolo é localizado pelo UUID do catálogo.
2. Confere-se que a empresa o liberou (`ativo = true`).
3. A linha do usuário é criada, ou reativada com `em_uso = true`.

### Desabilitar

1. A linha do usuário precisa existir.
2. Recusado se a empresa o tornou obrigatório ou se é o padrão da instituição.
3. Grava `em_uso = false` e **libera o padrão pessoal** do protocolo, e o escopo volta ao padrão da instituição.

### Definir padrão pessoal

1. Escopo válido; protocolo liberado pela empresa e compatível com o escopo.
2. O protocolo precisa estar em uso.
3. Se outro protocolo ocupava o padrão daquele escopo, ele é liberado **na mesma transação** que grava o novo. Se a segunda gravação falhar, nada é alterado, e o usuário não fica sem padrão nenhum.

### Remover padrão pessoal

Libera o padrão pessoal sem desabilitar o protocolo. O escopo passa a seguir o padrão da instituição, e ninguém fica sem padrão.

### Concorrência

Cliques duplos ou requisições simultâneas podem tentar gravar a mesma linha ou o mesmo padrão de escopo. A violação de unicidade no banco é convertida em um conflito (`409`) com a mensagem "Operação simultânea detectada. Tente novamente.", em vez de erro interno.

Na criação da configuração, a disputa entre duas requisições é resolvida sem erro: uma cria e a outra usa a configuração já criada.

## Qual protocolo a consulta carrega por padrão

Para um escopo pedido, a cadeia vai do mais específico ao mais geral e para no primeiro acerto:

| Ordem | Origem | Critério |
|---|---|---|
| 1 | `pessoal` | Padrão pessoal do escopo, se o protocolo está em uso e ainda liberado pela empresa |
| 2 | `pessoal` | Padrão pessoal `ambos` (quando o escopo pedido não é `ambos`) |
| 3 | `institucional` | Padrão da instituição para o escopo |
| 4 | `institucional` | Padrão da instituição `ambos` |
| 5 | `primeiro_liberado` | Primeiro protocolo liberado que sirva ao escopo, com os favoritos na frente |

Se a empresa desativar um protocolo depois de o usuário ter escolhido como padrão, ele deixa de contar e o padrão "cai" para o próximo da cadeia. Se nenhum protocolo liberado servir ao escopo, a consulta não tem padrão a carregar.

## Estado pessoal para o catálogo

A página de catálogo recebe, numa única consulta, o estado de cada protocolo (`em_uso` e `escopo_default`) para pintar a estrela dos cards. Essa leitura **não cria** a configuração: quem nunca abriu as configurações simplesmente não tem favoritos.
