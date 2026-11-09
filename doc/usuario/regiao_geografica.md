# Fluxo de Regiões Geográficas

Documentação do domínio de regiões geográficas do Bion: o cadastro de unidades territoriais (municípios, estados etc.), a criação automática de municípios a partir do código IBGE e a resolução de CEP em endereço e região.

---

# Contexto e conceitos

## Visão geral

Uma **região geográfica** é uma unidade territorial usada em agregações (ex.: avaliação de endemias por município ou por bairro) sem precisar guardar nem expor o CEP completo do paciente ou da empresa. O CEP completo continua onde já está (Empresa, Paciente); o domínio de região só devolve o que for pedido dele.

| Campo | Descrição |
|---|---|
| `nome_regiao` | Nome da unidade (ex.: "São Paulo") |
| Tipo | Município, estado etc., guardado na tabela de tipos de jurisdição |
| `codigo_ibge` | Código IBGE da unidade (7 dígitos para município) |
| `uf` | Sigla do estado |
| `latitude_centroide` / `longitude_centroide` | Centroide da unidade |
| `populacao_estimada` | População estimada mais recente |

### Tipo da região

O tipo não é uma coluna de texto na região: vive na tabela de **tipos de jurisdição**, ligada por chave estrangeira. O campo `codigo` dessa tabela guarda a mesma string que o enum antigo usava (`municipio`, `estado` etc.). Por isso:

- listar por tipo faz um JOIN com a tabela de tipos e filtra por `codigo`;
- criar uma região exige informar o `codigo` do tipo, que é resolvido para a chave estrangeira.

## Camadas e arquivos

| Arquivo | Responsabilidade |
|---|---|
| `controller.py` | Rotas HTTP de listagem e consulta de regiões |
| `service.py` | Cadastro, criação automática de municípios e consultas ao IBGE |
| `cep_service.py` | Resolução de CEP em endereço, código IBGE, coordenadas e região |
| `repository.py` | Consultas ao banco, incluindo a busca por tipo |

## Fontes externas

Nenhum dado de território é digitado: tudo vem de fontes públicas.

| Fonte | Usada para | Prazo máximo |
|---|---|---|
| API de localidades do IBGE | Confirmar o município e obter nome, código e UF | 5 s |
| Tabela SIDRA 6579, variável 9324 (IBGE) | População estimada do município, sempre o último período disponível | 5 s |
| Dataset aberto `kelvins/Municipios-Brasileiros` (CSV) | Centroides dos ~5.570 municípios | 10 s |
| BrasilAPI v2 | CEP: bairro, logradouro, código IBGE e coordenadas | 5 s |
| ViaCEP | Fallback do CEP: bairro, logradouro e código IBGE (sem coordenadas) | 5 s |

O IBGE não expõe um endpoint simples de centroide pronto (só a malha completa), por isso os centroides vêm de um dataset estático.

## Tolerância a falhas

As consultas externas **nunca lançam exceção** para quem chamou. Erro de rede, tempo esgotado, status diferente de 200, corpo que não é JSON ou resposta inesperada viram "sem dado":

| Dado | Se a consulta falhar |
|---|---|
| Município no IBGE | A região não é criada (resultado "não encontrada") |
| População estimada | A região é criada sem população |
| Centroide | A região é criada sem coordenadas |
| CEP na BrasilAPI | Tenta o ViaCEP |
| CEP nas duas fontes | Resultado "não encontrado", sem guardar no cache (ver cache de CEP) |

População e centroide são dados "melhor com, mas não essenciais": a ausência deles não impede o cadastro.

---

# Criação automática de município

Usada quando se pede uma região por código IBGE (ou por CEP, que se resolve em código IBGE) e ela ainda não existe no banco.

1. **Busca local.** Se o código já existe no banco, a região é devolvida direto, sem nenhuma consulta externa.
2. **Validação do formato.** O código precisa ter exatamente 7 dígitos. Outro formato não chega a ser consultado no IBGE (as rotas o recusam antes, como dados inválidos).
3. **Confirmação no IBGE.** A API de localidades devolve nome, código e UF. Se o município não existir lá, a região não é criada.
4. **Tipo "municipio".** A tabela de tipos de jurisdição precisa ter o tipo `municipio` cadastrado; sem ele não há como persistir a região.
5. **Centroide.** Buscado no dataset de municípios, que é baixado **uma vez por processo** e guardado em memória.
6. **População.** Consultada na tabela SIDRA 6579.
7. **Gravação.** A região é salva com todos os dados obtidos.

### Disputa na gravação

Se a gravação falhar, a transação é desfeita e a região é procurada de novo: outra requisição pode ter cadastrado o mesmo município no meio-tempo, e nesse caso essa região é devolvida. Se não existir, o resultado é "não encontrada".

### Cache de centroides

O CSV é baixado na primeira necessidade e guardado em memória no nível do módulo, porque raramente muda (municípios novos são raríssimos) e baixá-lo a cada cadastro seria desperdício. O cache é **por processo**: com vários workers, cada um mantém o seu. Se o download falhar, nada é guardado e a próxima tentativa baixa de novo.

---

# Resolução de CEP

## Endereço por CEP

1. **Formato.** O CEP é limpo e validado, e precisa ter 8 dígitos; um formato inválido resulta em "não encontrado" (a rota o recusa antes, como dados inválidos).
2. **Cache.** Se o CEP já foi resolvido neste processo, devolve o resultado guardado: o endereço encontrado ou o "não encontrado" definitivo.
3. **BrasilAPI v2** (fonte primária): devolve bairro, logradouro, código IBGE do município (em `ibge.city`) e coordenadas (em `location.coordinates`, quando presentes).
4. **ViaCEP** (fallback), usado se a BrasilAPI falhar ou não encontrar o CEP: devolve bairro, logradouro e código IBGE. O ViaCEP responde 200 com `{"erro": true}` para CEP inexistente, e isso é tratado como "não encontrado".
5. **Guarda no cache** o resultado definitivo (ver abaixo) e devolve uma cópia, para quem recebe poder alterar o resultado sem afetar o cache.

Formato do resultado:

| Campo | Descrição |
|---|---|
| `bairro` | Bairro, ou `None` |
| `logradouro` | Rua, ou `None` (CEP "geral" de cidade pequena não tem rua) |
| `codigo_ibge` | Código IBGE do município, ou `None` |
| `latitude` / `longitude` | Coordenadas, ou `None` |

**As coordenadas só vêm da BrasilAPI.** Quando o resultado vem do ViaCEP, `latitude` e `longitude` são sempre `None`. Mesmo na BrasilAPI, nem todo CEP tem coordenadas.

## Atalhos

| Método | Devolve | Observação |
|---|---|---|
| `buscar_bairro_por_cep` | Bairro | |
| `buscar_logradouro_por_cep` | Rua | `None` em CEP "geral" |
| `buscar_codigo_ibge_por_cep` | Código IBGE do município | |
| `buscar_coordenadas_por_cep` | `{"latitude", "longitude"}` | `None` se não houver coordenadas (ex.: resultado do ViaCEP) |

## Região por CEP

1. O CEP é resolvido em código IBGE.
2. Sem código IBGE (CEP inválido, inexistente ou sem município), o resultado é "não encontrada".
3. Com código, aplica-se a criação automática de município descrita acima.

## Cache de CEP

Muitos pacientes e empresas compartilham o mesmo CEP, então o resultado é guardado em memória, por CEP limpo. Cada consulta termina em um de três resultados, e só os dois primeiros entram no cache:

| Resultado | Quando | Vai para o cache? |
|---|---|---|
| Endereço encontrado | A BrasilAPI ou o ViaCEP devolveu o CEP | Sim |
| "Não encontrado" definitivo | As **duas** fontes confirmaram que o CEP não existe (BrasilAPI com 404 e ViaCEP com 404 ou `{"erro": true}`) | Sim |
| Falha | Pelo menos uma fonte falhou (rede, tempo esgotado, outro status HTTP, JSON inesperado) e nenhuma achou o CEP | **Não**: a próxima chamada consulta de novo |

Assim, uma queda passageira das APIs não faz um CEP válido ficar como "não encontrado" até o processo reiniciar. O cache é **por processo**, igual ao de centroides: com vários workers, cada um mantém o seu.

---

# Privacidade

Mesmo bairro e município sendo uma generalização do CEP, "bairro + condição de saúde" ainda pode ser dado pessoal sensível, dependendo do volume de casos no bairro (k-anonimato). O domínio de região só resolve CEP em bairro, código IBGE e coordenadas. **Como agregar e expor isso em relatórios** (ex.: um limiar mínimo de casos antes de exibir) é responsabilidade de quem consome o serviço, e não deste módulo.

---

# Listagem paginada

A listagem de regiões é paginada, de **15 em 15** por padrão, em ordem alfabética pelo nome (com o id como desempate, o que mantém as páginas estáveis entre uma chamada e outra).

| Parâmetro | Padrão | Regra |
|---|---|---|
| `page` | 1 | A partir de 1; valores menores ou inválidos viram 1 |
| `limit` | 15 | Vazio ou não positivo volta a 15; o máximo é 50 |
| `tipo` | todos | Código do tipo de jurisdição, ex.: `municipio` |

O total devolvido é a contagem de **todas** as regiões do filtro, e não só as da página.