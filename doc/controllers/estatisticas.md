# Estatísticas

Documentação das rotas de estatísticas do Bion (dashboards) e do campo de interpretação que acompanha as métricas.

---

# Contexto e conceitos

## Visão geral

As estatísticas respondem perguntas sobre a operação, a qualidade da IA, o perfil epidemiológico, a segurança medicamentosa e o histórico clínico da base de pacientes de **uma empresa**. Todas as rotas:

- são `GET`;
- exigem login; o bloco operacional exige perfil **admin** (ver "Acesso" em Rotas);
- calculam sobre a **empresa da sessão** (não há parâmetro de empresa);
- aceitam parâmetros opcionais pela query string, como o período em dias e o limite de itens.

A única exceção quanto à empresa é D1 (interações medicamentosas), que consulta dados globais do catálogo.

## Camadas

| Camada | Papel |
|---|---|
| Controller | Lê a query string, chama o service e devolve a resposta |
| Service (fachada) | Um método por métrica; repassa ao serviço da área correspondente |
| Serviços por área | Calculam a métrica e montam a interpretação (usuários, pacientes, consultas, atendimentos, alergias, prescrições, saídas da IA, protocolos) |
| Helper de interpretação | Níveis, textos e comparação com o período anterior, compartilhados |

## Parâmetros de query

| Parâmetro | Significado | Observação |
|---|---|---|
| `dias` | Período analisado, contado para trás a partir de agora | De 1 a 365. O padrão varia por rota (ver tabelas) |
| `limite` / `top` | Quantidade máxima de itens do ranking | De 1 a 50. O padrão varia por rota |

Valor ausente ou que não seja número inteiro é ignorado e vale o padrão da rota. Valor inteiro **fora da faixa** (por exemplo, `dias=0`, `dias=-5` ou `dias=100000`) é rejeitado com erro de validação.

## Formato das respostas

- Sucesso: `json_success` com `data`. A estrutura de `data` é definida pelo serviço de cada métrica; as que trazem interpretação incluem o campo `interpretacao` (abaixo).
- Erro: exceções de negócio (`BionException`, incluindo o erro de validação dos parâmetros) devolvem `json_error` com a mensagem e o status da exceção. Qualquer outra exceção não é tratada pelas rotas e segue para o tratamento global de erros da aplicação. Falta de login ou de perfil é tratada pelos decorators de sessão.

---

# Interpretação das métricas

Métricas que trazem interpretação incluem o campo `interpretacao`:

| Campo | Conteúdo |
|---|---|
| `direcao` | `alto_bom` (mais é melhor), `alto_ruim` (mais é pior) ou `neutro` |
| `texto` | Explicação do resultado em linguagem natural |
| `nivel` | Classificação do valor, ou `null` quando a métrica não tem limiar absoluto |
| `comparacao` | Texto de comparação com o período anterior, ou `null` sem base de comparação |

## Níveis

Aplicados a métricas percentuais (0 a 100):

| Valor | Nível |
|---|---|
| 85 ou mais | `otimo` |
| 70 a 84 | `bom` |
| 60 a 69 | `ok` |
| 50 a 59 | `medio` |
| 40 a 49 | `medio_ruim` |
| abaixo de 40 | `ruim` |

Quando a direção é `alto_ruim` (por exemplo, % de abandono ou de reações alérgicas graves), a escala é **invertida**: o nível é calculado sobre `100 - valor`. Assim, 5% classifica como `otimo` e 90% como `ruim`.

Em métricas percentuais, a direção só pode ser `alto_bom` ou `alto_ruim`; qualquer outro valor é um erro de programação e levanta `ValueError`.

Métricas de volume, contagem ou tempo, sem limiar absoluto, trazem `nivel = null` (não existe "85 atendimentos é ótimo"), mas podem ter `direcao` e `comparacao`.

## Comparação com o período anterior

O **período anterior** tem a mesma duração do atual e vem imediatamente antes dele, sem sobreposição. Para `dias = 30`, o atual cobre os últimos 30 dias e o anterior cobre os 30 dias que o precedem.

| Situação | `comparacao` |
|---|---|
| Valor subiu | "Aumento de X% em comparação com o período anterior" |
| Valor caiu | "Queda de X% em comparação com o período anterior" |
| Variação zero | "Sem variação em comparação com o período anterior" |
| Sem valor atual, sem valor anterior ou anterior igual a 0 | `null` |

X é a variação percentual arredondada a uma casa decimal.

---

# Rotas

Os caminhos são relativos ao prefixo do blueprint `estatisticas`, registrado no `main.py`.

## Acesso

| Bloco | Exige |
|---|---|
| Geral e Operacional (inclui E2 e F3) | Admin (`@requer_admin`) |
| Qualidade da IA: B4 (versões em uso) e E3 (correlação) | Admin (`@requer_admin`) |
| Qualidade da IA: B1 (confiança) e B2 (completude) | Login (`@requer_login()`) |
| Epidemiológico | Login (`@requer_login()`) |
| Farmacovigilância e segurança do paciente (inclui F4) | Login (`@requer_login()`) |
| Histórico clínico da base de pacientes | Login (`@requer_login()`) |

Todas as rotas consultam sempre a empresa da sessão.

## Geral

| Método | Rota | Descrição | Query |
|---|---|---|---|
| GET | `/geral` | Resumo: total de profissionais, pendentes, ativos, consultas de hoje e pacientes cadastrados | n/a |

## Operacional (A1-A5, E2, F3)

| Método | Rota | ID | Descrição | Query (padrão) |
|---|---|---|---|---|
| GET | `/atendimentos/volume` | A1 | Volume de atendimentos por dia | `dias` (30) |
| GET | `/atendimentos/tempo-medio` | A2 | Tempo médio de atendimento por tipo | `dias` (30) |
| GET | `/atendimentos/taxa-conclusao` | A3 | Taxa de conclusão vs. abandono: consultas encerradas concluídas contra evasões | `dias` (30) |
| GET | `/equipe/efetivo` | A4 | Efetivo ativo por papel | n/a |
| GET | `/equipe/engajamento` | A5 | Engajamento e atividade da equipe | `dias` (7) |
| GET | `/atendimentos/tendencia-eficiencia` | E2 | Tendência de eficiência acumulada | `dias` (30) |
| GET | `/pacientes/tipo-sanguineo` | F3 | Distribuição de tipo sanguíneo na base | n/a |

## Qualidade e confiabilidade da IA (B1, B2, B4, E3)

| Método | Rota | ID | Descrição | Query (padrão) |
|---|---|---|---|---|
| GET | `/ia/confianca-media` | B1 | Confiança média da IA | `dias` (30) |
| GET | `/ia/completude-media` | B2 | Completude média dos dados de entrada | `dias` (30) |
| GET | `/ia/versoes-em-uso` | B4 | Versões do modelo de IA em uso | `dias` (30) |
| GET | `/ia/correlacao-completude-confianca` | E3 | Correlação entre completude e confiança | `dias` (30) |

## Epidemiológico (C1-C5)

| Método | Rota | ID | Descrição | Query (padrão) |
|---|---|---|---|---|
| GET | `/epidemiologico/top-cid-regiao` | C1 | Doenças (CID) mais comuns por região | `dias` (14), `limite` (10) |
| GET | `/epidemiologico/evolucao-cid/<codigo_cid10>` | C2 | Evolução temporal de um CID | `dias` (30) |
| GET | `/epidemiologico/incidencia-regiao` | C3 | Incidência por 100 mil habitantes, por região | `dias` (14) |
| GET | `/epidemiologico/tempo-ate-atendimento` | C4 | Tempo entre sintoma e busca por atendimento | `dias` (30) |
| GET | `/epidemiologico/queixas-frequentes` | C5 | Queixas principais mais frequentes | `dias` (30), `top` (15) |

Parâmetro de caminho: `codigo_cid10` (texto), o código CID-10 a analisar.

## Farmacovigilância e segurança do paciente (D1-D4, F4)

| Método | Rota | ID | Descrição | Query (padrão) |
|---|---|---|---|---|
| GET | `/medicamentos/interacoes-gravidade` | D1 | Interações medicamentosas cadastradas, por gravidade (dado global) | n/a |
| GET | `/alergias/top-substancias` | D2 | Alergias mais reportadas, por substância | `limite` (10) |
| GET | `/alergias/<substancia>/gravidade` | D2 (detalhe) | Gravidade das reações a uma substância | n/a |
| GET | `/alergias/gravidade-geral` | F4 | Gravidade geral das reações alérgicas, sem filtro por substância | n/a |
| GET | `/exames/urgencia-por-origem` | D3 | Urgência de exames: IA vs. profissional | `dias` (30) |
| GET | `/medicamentos/top-por-classe` | D4 | Medicamentos mais prescritos por classe | `dias` (30), `limite` (10) |
| GET | `/medicamentos/top-por-classe/<classe>` | D4 (detalhe) | Princípios ativos mais prescritos dentro de uma classe | `dias` (30), `limite` (10) |

Parâmetros de caminho: `substancia` (texto) e `classe` (texto).

## Histórico clínico da base de pacientes (F1-F2)

| Método | Rota | ID | Descrição | Query (padrão) |
|---|---|---|---|---|
| GET | `/pacientes/doencas-cronicas-top` | F1 | Doenças crônicas mais comuns na base | `limite` (10) |
| GET | `/pacientes/uso-continuo-medicacao` | F2 | Percentual de pacientes em uso contínuo de medicação | n/a |

---

# Catálogo de métricas

O catálogo prevê três métricas que **ainda não foram implementadas**: **B3** (concordância médico × IA), **E1** (índice de qualidade total) e **E4** (painel de alerta epidemiológico composto). Por isso a numeração tem lacunas nos grupos B e E.