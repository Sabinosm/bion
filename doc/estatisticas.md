# Fluxo de cálculo e interpretação das estatísticas

Como cada métrica das estatísticas é calculada, que texto e que interpretação ela devolve e o que acontece quando não há dados. Para as rotas e parâmetros, ver `estatisticas.md`.

---

# Visão geral do fluxo

```
Rota (controller) -> EstatisticasService (fachada) -> serviço da área (Estatisticas*) -> serviço de domínio
```

| Etapa | O que faz |
|---|---|
| Rota | Lê `dias`, `limite` ou `top` da query string e a empresa da sessão |
| Fachada | Um método por métrica; repassa ao serviço da área correspondente |
| Serviço da área | Pede os dados brutos ao serviço de domínio (consultas, atendimentos, alergias, prescrições, usuários etc.), calcula a métrica e monta `leitura` e `interpretacao` |
| Serviço de domínio | Acessa os dados (consultas agrupadas por dia, por status, médias, rankings) |

## Serviços de área

| Serviço | Métricas |
|---|---|
| `EstatisticasUsuario` | Geral (contagens), A4, A5 |
| `EstatisticasConsulta` | Geral (consultas de hoje), A1, A3 |
| `EstatisticasAtendimento` | A2, E2, C4 |
| `EstatisticasPaciente` | Geral (pacientes), F1, F2, F3 |
| `EstatisticasAlergia` | D2, D2 (detalhe), F4 |
| `EstatisticasOutputBion` | B1, B2, B4, E3 |
| `EstatisticasResultadoPrescricao` | C1, C2, C3 |
| `EstatisticasInputProtocolo` | C5 |
| `EstatisticasPrescricaoExame` | D3 |
| `EstatisticasPrescricao` | D4, D4 (detalhe) |
| `EstatisticasInteracoesMedicamentos` | D1 |

---

# Anatomia da resposta

Cada métrica devolve os **dados** próprios (série, ranking, distribuição, média) e, em geral, dois campos de apoio:

| Campo | Conteúdo |
|---|---|
| `leitura` | Frase pronta que resume o resultado. É `null` quando não há dados |
| `interpretacao` | `{direcao, texto, nivel, comparacao}` (ver `estatisticas.md`). Nem toda métrica tem; as puramente informativas só trazem `leitura` |

## Quais métricas trazem interpretação

| Modelo de interpretação | Métricas |
|---|---|
| **Percentual com nível**, mais é melhor | A3 (taxa de conclusão), B1 (confiança), B2 (completude) |
| **Percentual com nível**, mais é pior | D2 detalhe (% de reações graves por substância), F4 (% geral de reações graves) |
| **Sem nível, com comparação com o período anterior** | A1 (volume), A2 (tempo médio), E2 (tendência), C2 (evolução de CID) |
| **Sem nível, com comparação própria** | A5 (proporção de inativos sobre o efetivo ativo) |
| **Sem nível e sem comparação** (só direção e texto) | C1, C3, D3, D4, F1, E3 |
| **Sem interpretação** (só `leitura`) | A4, B4, C4, C5, D1, D2 (ranking), D4 detalhe, F2, F3 |

---

# Níveis e comparação (mecanismo compartilhado)

## Classificação em nível

O valor percentual é classificado por faixas: 85 ou mais `otimo`, 70+ `bom`, 60+ `ok`, 50+ `medio`, 40+ `medio_ruim`, abaixo de 40 `ruim`.

Para métricas em que valor alto é ruim (`direcao = "alto_ruim"` com nível), o nível é calculado sobre `100 - valor`: 5% de reações graves é `otimo`; 90% é `ruim`.

## Comparação com o período anterior

1. O serviço da área obtém o valor do **período atual** pelo serviço de domínio.
2. Obtém o valor do **período anterior** chamando a versão "por período" do mesmo método, com a janela imediatamente anterior e de mesma duração (para `dias = 30`, de 60 a 30 dias atrás).
3. Compara os dois valores e gera o texto: "Aumento de X% ...", "Queda de X% ..." ou "Sem variação ...". Sem valor anterior (ausente ou zero) ou sem valor atual, `comparacao` é `null`.

O que é comparado em cada métrica:

| Métrica | Valor comparado |
|---|---|
| A1 | Total de consultas do período |
| A2 | Média geral do tempo de atendimento, ponderada pelo total de cada tipo |
| A3 | Percentual de conclusão |
| B1 / B2 | Média de confiança / média de completude |
| C2 | Total de casos do CID |
| E2 | Média geral do tempo de atendimento (a rota é a própria comparação) |

---

# Fluxo por métrica

## Equipe

### A4: efetivo ativo
1. Obtém a contagem de usuários ativos por papel.
2. `leitura`: "Equipe ativa: X médicos, Y enfermeiros, Z admins", incluindo só os papéis presentes, nessa ordem de prioridade.
3. Sem nenhum profissional ativo: "Nenhum profissional ativo no momento".

### A5: engajamento da equipe
1. Conta e lista os profissionais sem acesso ao sistema há mais de `dias`.
2. `leitura`: "N profissionais sem acesso ao sistema há mais de D dias".
3. Soma o efetivo ativo (todos os papéis) e calcula a proporção de inativos.
4. `interpretacao`: direção `alto_ruim`, sem nível. O campo `comparacao` traz a proporção ("N de M profissionais ativos (P%) estão sem acesso há mais de D dias"), e não um confronto com período anterior, porque não existe histórico de quem estava inativo em cada data. Sem efetivo ativo, `comparacao` é `null`.
5. `profissionais` traz a lista resumida dos inativos.

## Consultas

### A1: volume de atendimentos
1. Obtém a série diária de consultas iniciadas e soma o total do período.
2. Obtém o total do período anterior.
3. `leitura`: "Foram realizados N atendimentos nos últimos D dias".
4. `interpretacao`: direção `neutro`, sem nível, com comparação entre os totais. O texto orienta a ler o volume junto com o efetivo (A4) e o tempo médio (A2).

### A3: taxa de conclusão
1. Obtém a contagem de consultas **encerradas** por desfecho final (`alta`, `internacao`, `transferencia`, `obito`, `evasao`). Consultas ainda em andamento ficam de fora.
2. `abandonadas` são as encerradas com desfecho `evasao`; `concluidas` são todas as demais encerradas (qualquer outro desfecho, ou sem desfecho registrado). `total = concluidas + abandonadas`.
3. `percentual = concluidas / total * 100` (uma casa); sem consultas encerradas, `0.0`.
4. Calcula o percentual do período anterior da mesma forma; sem consultas encerradas no período anterior, fica sem valor e a comparação é `null`.
5. A resposta traz também `por_desfecho` (a contagem usada no cálculo) e `por_status` (consultas por status no período, incluindo as em andamento).
6. `leitura`: "X% das consultas encerradas foram concluídas, sem evasão (N evasões no período)".
7. `interpretacao`: direção `alto_bom`, com nível e comparação.

## Atendimentos

### A2: tempo médio de atendimento
1. Obtém a duração média e o total por tipo de atendimento; acrescenta `media_formatada` (formato "XminYYs").
2. `leitura`: tempo médio do tipo com mais atendimentos.
3. Calcula a **média geral ponderada** pelo total de cada tipo, no período atual e no anterior.
4. `interpretacao`: direção `alto_ruim` (menor tempo é melhor), sem nível (o tempo ideal varia por tipo), com comparação entre as médias gerais.
5. **Aviso de mistura de profissionais**: obtém os tempos segmentados por grupo (`mesmo_profissional` e `transferencia`) e calcula a proporção de `mesmo_profissional`. Se for de **30% ou mais**, `aviso_mistura_profissional` traz a proporção, o detalhamento por grupo (com média formatada) e uma leitura sugerindo olhar os grupos separadamente. Abaixo disso, ou sem dados classificáveis, é `null`.
6. Sem dados no período: `por_tipo` vazio e todo o restante `null`.

### E2: tendência de eficiência
1. Obtém os tempos por tipo dos dois períodos consecutivos e calcula a média ponderada de cada um.
2. `variacao_percentual = (atual - anterior) / anterior * 100` (uma casa).
3. `leitura`: "A equipe está X% mais rápida" (variação negativa) ou "mais lenta" (variação positiva), "nos últimos D dias, comparado aos D dias anteriores". Com variação exatamente zero: "Sem variação no tempo de atendimento nos últimos D dias, comparado aos D dias anteriores".
4. `interpretacao`: direção `alto_ruim`, sem nível, com comparação.
5. Casos sem dados:

| Situação | Resultado |
|---|---|
| Sem média no período atual | Tudo `null` (os períodos vêm como obtidos) |
| Sem média no período anterior | `variacao_percentual` `null`, `leitura` = "Sem dados suficientes no período anterior para comparação", sem interpretação |

### C4: tempo até o atendimento
1. Obtém a média, em horas, entre o início dos sintomas e o atendimento.
2. `media_horas` arredondada a uma casa; `null` sem dados.
3. `leitura` em horas se a média for menor que 24h; a partir de 24h, convertida para dias (uma casa).

## Pacientes

### F1: doenças crônicas mais comuns
1. Obtém o ranking de CIDs crônicos ativos (acumulado da base, sem filtro de período).
2. `leitura`: condição mais comum e quantos pacientes a têm.
3. `interpretacao`: neutra, sem nível e sem comparação, sempre presente.

### F2: uso contínuo de medicação
1. Obtém do serviço o total de pacientes, quantos estão em uso contínuo e o percentual.
2. A resposta repassa esses campos e acrescenta `leitura` ("X% dos pacientes cadastrados estão em uso contínuo de medicação").

### F3: tipo sanguíneo
1. Obtém a distribuição por tipo.
2. `leitura`: tipo mais comum e seu percentual entre os pacientes **com tipo registrado**. Sem registros, `null`.

## Alergias

### D2: substâncias mais reportadas
Ranking de substâncias com `leitura` apontando a mais reportada e o total de casos. Sem interpretação.

### D2 (detalhe) e F4: gravidade das reações
1. Obtém a contagem de reações por gravidade (para uma substância, ou para toda a base no F4).
2. `pct = reações "grave" / total * 100` (uma casa).
3. `leitura`: percentual de reações classificadas como graves.
4. `interpretacao`: direção `alto_ruim` com nível (escala invertida) e sem comparação, pois o cadastro é acumulado e não tem filtro de período.
5. Sem nenhuma reação registrada: `leitura` e `interpretacao` `null`.

## Qualidade da IA

### B1 e B2: confiança e completude médias
1. Obtém a média do período. Sem execuções: `media` `null`, `leitura` "Sem execuções da IA no período" e sem interpretação.
2. Com média, obtém a do período anterior.
3. `media` é arredondada a duas casas; a leitura usa uma casa.
4. `interpretacao`: direção `alto_bom`, com nível e comparação.

### B4: versões do modelo em uso
Lista as versões usadas no período. `leitura`: se há uma só, "Todas as execuções usaram o modelo X"; se há várias, o número de versões e a predominante (a primeira da lista) com o total de execuções. Sem interpretação.

### E3: correlação entre completude e confiança
1. Obtém os pares (completude, confiança) das execuções do período.
2. Menos de 2 pares: "Amostra insuficiente para calcular correlação".
3. Calcula o coeficiente de Pearson (3 casas). Se completude ou confiança não variam, o coeficiente não existe: "Sem variação suficiente nos dados para calcular correlação".
4. Rótulo de força e sentido na `leitura`, pela força **absoluta** do coeficiente (que vai de -1 a 1):

| Valor absoluto do coeficiente | Força |
|---|---|
| 0,7 ou mais | forte |
| 0,4 a 0,69 | moderada |
| 0,1 a 0,39 | fraca |
| abaixo de 0,1 | praticamente nula (sem sentido) |

Fora do caso "praticamente nula", o rótulo acrescenta o sentido: coeficiente positivo é "positiva" (ex.: "forte positiva") e negativo é "negativa" (ex.: "moderada negativa").

5. `interpretacao`: direção `neutro`, sem nível e sem comparação. O texto lembra que correlação não indica causalidade; para coeficiente de -0,1 ou menos, o texto aponta que mais completude coincide com menor confiança e que vale investigar.

## Epidemiológico

### C1: CIDs mais comuns por região
Ranking de CID por região no período. `leitura` destaca o primeiro (pacientes, doença, CID e região). Interpretação neutra, sem nível e sem comparação.

### C2: evolução de um CID
1. Obtém a série do CID e soma o total do período; obtém o total do período anterior.
2. `leitura`: "N casos de CID registrados nos últimos D dias" ou "Nenhum caso de CID registrado ...".
3. `interpretacao`: neutra, sem nível, com comparação entre os totais. O texto alerta que aumento acentuado pode indicar surto e queda pode indicar melhora ou subnotificação.

### C3: incidência por região
1. Obtém os casos por região no período.
2. A população estimada de cada região já vem junto com os casos, na mesma consulta.
3. `incidencia_por_100mil = casos / população * 100.000` (uma casa). Região sem população cadastrada fica com `null` (não se assume zero).
4. Ordena da maior incidência para a menor, deixando as regiões sem incidência por último.
5. `leitura` só existe se a primeira região tem incidência. Interpretação neutra, sem nível e sem comparação.

### C5: queixas mais frequentes
1. Obtém as queixas principais do período.
2. Cada queixa é quebrada em palavras: minúsculas, apenas letras (com acentos), sem palavras comuns (de, da, com, para...) e só com mais de 2 letras.
3. Cada palavra conta **uma vez por queixa**, mesmo que apareça repetida.
4. Devolve as `top` palavras mais frequentes e o total de queixas analisadas. A contagem é por palavra, não por frase.

## Farmacovigilância

### D1: interações medicamentosas
Conta as interações cadastradas por gravidade e o total. É um dado de referência global: não depende de empresa nem de período. `leitura` só existe se há interações.

### D3: urgência dos exames por origem
1. Obtém a contagem de exames por urgência e origem da sugestão (IA ou profissional).
2. Soma o total de cada nível de urgência e calcula, para cada linha, o `percentual` dentro do seu nível (uma casa).
3. `leitura` só trata dos exames `urgente`: "X% pela origem ...", uma parte por origem.
4. `interpretacao`: neutra, sem nível e sem comparação.

### D4: medicamentos por classe
- **Ranking de classes**: `leitura` aponta a classe mais prescrita; interpretação neutra, sem nível e sem comparação.
- **Detalhe por classe**: ranking de princípios ativos dentro da classe informada; só `leitura`, sem interpretação.