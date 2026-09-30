# Fluxo do Protocolo Composto

Documentação da família de raciocínio "composição de módulos", que implementa o segundo caso descrito em *Fluxo de Protocolos Clínicos*: o único ponto do sistema onde um protocolo nasce dentro da aplicação, por combinação de blocos já validados — nunca por JSON livre, nunca por código novo.

---

# Contexto e conceitos

## O que o protocolo composto resolve

As demais famílias (árvore, soma ponderada) tratam "o protocolo" como uma unidade indivisível: uma Strategy, uma estrutura, um cálculo. Isso funciona bem quando o protocolo *é* um instrumento publicado por um órgão. Mas boa parte do trabalho clínico real não é um instrumento só — é a combinação de vários rastreios menores decididos por quem monta a rotina de atendimento (polifarmácia + risco de queda + estado nutricional, por exemplo). O protocolo composto existe para esse caso, sem abrir uma segunda porta de entrada de conteúdo não revisado.

A peça central da modelagem é o **módulo**: um bloco de raciocínio clínico menor que o protocolo, mas grande o suficiente para ser executado e interpretado sozinho. Um módulo nunca é metade de uma pergunta — ele é uma pergunta clínica completa ("qual o risco por comorbidades?", "há sinais de sepse?"), só que menor que um protocolo inteiro. Cada família (pontuador, classificador, regra) já foi descrita no desenho do sistema como uma forma matemática de raciocínio; um módulo é uma instância de uma dessas formas, independente de qualquer outro módulo.

## Nenhum protocolo é criado por usuário — nem este

O nome "composto" descreve a *forma de raciocínio* da Strategy, não a origem do conteúdo. Como todo o resto do catálogo, um protocolo composto nasce por seed, sob a mesma governança clínica dos protocolos oficiais. A diferença para o NEWS2 ou o MTS não é *quem aprova o conteúdo* — é *como o cálculo é feito*: em vez de uma tabela de pesos própria, a Strategy delega a módulos menores, que por sua vez são eles mesmos protocolos-oficiais-em-miniatura, cada um com sua própria explicação, referência bibliográfica e versão.

"Personalização" aqui significa **seleção e combinação** de peças curadas, nunca autoria de conteúdo clínico. O usuário final não escreve faixas, não escreve regras, não escreve explicação — ele só vê o protocolo já pronto no catálogo, exatamente como veria o NEWS2. Isso mantém a garantia central do sistema (nenhuma rota da aplicação escreve na estrutura de um protocolo em runtime) intacta mesmo para esta família.

## Módulos são independentes por desenho — essa é a restrição que sustenta tudo

Um módulo recebe um conjunto fechado de variáveis de entrada e devolve um resultado tipado e determinístico, **sem depender de nenhum outro módulo para ser executado**. Essa independência não é um detalhe de implementação — é a premissa que permite:

- testar cada módulo isoladamente, com casos de valores dourados tirados da publicação original do instrumento;
- adicionar um módulo novo sem tocar em nenhum módulo existente;
- reaproveitar o mesmo módulo em protocolos diferentes (o mesmo PHQ-9 pode compor uma triagem de saúde mental e uma avaliação geriátrica);
- garantir que a saída de um módulo nunca vira entrada de outro — a única exceção permitida a essa regra é a relação de **gatilho**, tratada como controle de execução, nunca como encadeamento de dado.

O contrato único de resultado descrito para o sistema como um todo (classificação, trilha explicativa, dados ausentes, metadados) vale também dentro de cada módulo: cada família de módulo devolve a mesma forma, e o que for peculiar de uma família — um total numérico, o motivo de um alerta — vive nos metadados do módulo, nunca no nível raiz da resposta do protocolo composto.

## Três formas de módulo, e por que a lista fica curta de propósito

Módulo é definido pelo contrato de saída, não pelo tema clínico. Isso mantém o motor pequeno mesmo com dezenas de instrumentos diferentes:

| Família de módulo | Entrada → saída | Exemplo |
|---|---|---|
| **Pontuador** | campos → soma de pontos, com faixas de interpretação | PHQ-9, GAD-7, escore de Wells |
| **Classificador** | campos → uma categoria | IMC, classificação de pressão arterial |
| **Regra / Gatilho** | condições → um flag com motivo | Alerta de polifarmácia, elegibilidade etária |

A tag de domínio clínico (epidemiológico, comorbidade, institucional) é só um rótulo de organização — o que o motor usa de fato é a família de cálculo. Isso significa que adicionar a próxima família de módulo (depois de pontuador, classificador e regra) segue a mesma lógica de extensão descrita para o sistema inteiro: uma implementação nova da interface comum, e uma entrada nova no registro — nenhuma família existente é tocada.

## A linguagem de condição é uma só, e é deliberadamente pequena

Classificador-por-regras e regra/gatilho compartilham a mesma sintaxe de condição: comparações simples (`<`, `<=`, `>`, `>=`, `==`, `!=`, `em`, `nao_em`) combinadas por `e`/`ou`/`nao`. Não há aritmética, não há referência a outro módulo, não há função. Essa restrição é o que torna cada condição auditável a olho e o que garante que o determinismo do sistema não dependa de revisar código a cada módulo novo — só de revisar um JSON pequeno.

Uma consequência dessa escolha, e que molda todo o resto do desenho: **variável ausente não é o mesmo que variável falsa**. Se "idade ≥ 60" não pode ser avaliado porque a idade não foi informada, o resultado é *desconhecido*, não *falso* — um alerta clínico não pode deixar de disparar silenciosamente só porque um campo não foi preenchido. Essa lógica de três valores (verdadeiro / falso / desconhecido) se propaga por toda combinação de condições: um `e` só resolve para falso se algum termo for concretamente falso, nunca só porque falta dado; o inverso vale para o `ou`.

## O dicionário de variáveis é o que evita perguntar a mesma coisa duas vezes

Cada módulo declara os campos que usa, mas os campos em si vêm de um dicionário compartilhado entre todos os módulos do catálogo. Isso resolve o problema mais óbvio de combinar módulos: se dois módulos de um mesmo protocolo pedem "idade", o profissional preenche uma vez, não duas. O protocolo composto expõe ao front a **união** das variáveis de todos os seus módulos — nunca uma lista por módulo — preservando a promessa do sistema de que todo protocolo expõe seus campos de entrada num formato achatado só.

O dicionário também é o que torna o tipo de cada variável (numérico, categórico, booleano) uma verdade única: o mesmo "idade" não pode ser numérico num módulo e categórico em outro, e isso é verificado antes de qualquer módulo entrar em produção.

## Tudo é preenchido de uma vez — o funil vira regra de execução, não pergunta nova

Um protocolo com um módulo de elegibilidade seguido de módulos que só fazem sentido para quem é elegível parece pedir perguntas condicionais. O protocolo composto resolve isso sem quebrar a premissa de que a lista de campos é fixa antes do preenchimento começar: **o front pede todos os campos de todos os módulos de uma vez**, e é o backend, na hora de calcular, que decide quais módulos rodam.

O mecanismo é o **gatilho**: um módulo de papel `gatilho` (em geral, uma regra) é avaliado antes dos demais; conforme seu resultado, uma configuração própria do protocolo decide quais outros módulos ficam marcados como **não aplicáveis**, em vez de calculados. Um módulo não aplicável não é um dado ausente — é uma decisão consciente de que aquele módulo não deveria rodar para este paciente, e o motivo fica registrado no resultado. Nenhum gatilho pode desligar outro gatilho: a camada de controle de execução tem uma profundidade só, para não virar uma cadeia de dependências disfarçada de módulos independentes.

## Cada módulo é lido de forma independente — agregação é a exceção, não a regra

Por padrão, um protocolo composto não produz um número final: cada módulo devolve o seu resultado, e o protocolo simplesmente lista todos, lado a lado. Isso é o modo paralelo, e é o mais seguro, porque nunca inventa uma combinação sem respaldo clínico — somar o escore de um instrumento de saúde mental com uma classificação de pressão arterial não significa nada, e o sistema não tenta dar sentido a isso.

Quando módulos do mesmo tipo de saída pertencem ao mesmo grupo, uma agregação declarada explicitamente (soma de pontos, o maior valor, a categoria mais grave, ou "algum alerta disparou") produz um resultado combinado — sempre restrita a módulos compatíveis entre si, nunca misturando pontos com categorias. Um módulo que não pôde ser calculado nunca entra como zero silencioso numa soma: ele é excluído e a agregação é sinalizada como parcial, para que a ausência de dado nunca seja lida como ausência de risco.

## O que fica registrado quando o protocolo é composto

A cadeia de rastreabilidade descrita para o sistema inteiro — a execução aponta para a versão vigente do protocolo, nunca duplica conteúdo — se estende um nível a mais aqui: a versão do protocolo aponta para a composição de módulos vigente naquele momento, e a composição aponta para a versão específica de cada módulo. Publicar uma nova versão de um módulo não altera silenciosamente um protocolo composto já em uso — a composição referencia versões de módulo específicas, do mesmo jeito que uma execução referencia uma versão de protocolo específica.

Cada composição de módulos tem ainda um identificador derivado — nunca escrito à mão — que funciona como uma fotografia de quais módulos a compõem, útil para localizar rapidamente todos os protocolos que usam um módulo específico, ou para garantir que duas composições não sejam, sem querer, exatamente a mesma combinação sob nomes diferentes.

## Por que esta família também resiste a crescer mal

O orquestrador genérico do sistema — o que resolve permissão institucional, busca a versão vigente e persiste a execução — nunca precisa saber que, por baixo, um protocolo composto está delegando a três módulos diferentes. Ele enxerga a Strategy do composto exatamente como enxergaria a de um escore ponderado: carregar estrutura, validar respostas, executar, devolver o contrato único. A composição em si é só mais um nível de delegação dentro da Strategy — o mesmo princípio de "implementação que delega a outras, invisível para o que vem antes e depois dela na cadeia" que já sustentava o sistema antes desta família existir.