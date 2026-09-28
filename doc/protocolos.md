# Fluxo de Protocolos Clínicos

Documentação da arquitetura de execução de protocolos clínicos (escores, árvores de triagem, PCDTs), cobrindo o padrão Strategy que permite adicionar novos protocolos sem alterar código já existente, a cascata de liberação institucional, e o ciclo completo de pesquisa → preenchimento → cálculo → persistência.

---

# Contexto e conceitos

## Visão geral

O sistema precisa suportar múltiplos protocolos clínicos (escores numéricos como NEWS2, árvores de decisão como MTS, PCDTs, protocolos compostoss por composição de módulos) sem que adicionar um protocolo novo exija tocar no código dos protocolos já existentes. A resposta arquitetural é o padrão **Strategy**: cada família de raciocínio clínico — não cada protocolo individual — vira uma implementação própria, escolhida em tempo de execução por uma Factory a partir de um campo do banco (`tipo_protocolo`).

A unidade de generalização certa não é "o protocolo X" mas "a forma matemática do raciocínio": árvore de decisão (pergunta → resposta → próximo nó ou categoria final), soma ponderada com faixas (cada parâmetro vira pontos, soma total, interpreta o total), regra categórica (combinação de condições → conduta direta), e composição de módulos (protocolo montado pelo próprio usuário a partir de blocos declarativos). Dois protocolos publicados por órgãos diferentes, mas com a mesma forma de raciocínio, compartilham a mesma Strategy — só o conteúdo (parâmetros, faixas, pesos) muda, carregado do banco.

## Duas origens de protocolo, dois ciclos de vida diferentes

**Protocolo oficial** (escores publicados, PCDTs, árvores de triagem padronizadas) nasce fora da aplicação: é conteúdo versionado, aprovado por governança clínica, inserido via seed/migration, e **somente leitura em runtime**. Nenhuma rota da aplicação escreve na estrutura de um protocolo oficial — se a aplicação nunca escreve, o conteúdo não pode ser corrompido pela aplicação. Isso vale tanto para a identidade do protocolo (nome, sigla, órgão emissor, versão vigente) quanto para sua lógica interna (parâmetros e faixas, estrutura de árvore, regras de categoria).

**Protocolo composto** nasce dentro da aplicação, por composição de módulos declarativos que o próprio usuário monta — nunca por JSON livre ou código. É o único caminho onde existe uma tela de "criar protocolo".

## Contrato único de resultado

Toda Strategy, não importa a família, devolve exatamente a mesma forma de resultado: uma classificação final, uma trilha explicativa (o que pesou na decisão, em ordem), os dados que ficaram ausentes, e um espaço de metadados livre para o que for específico daquela família. Nenhuma família pode adicionar campo de primeira classe fora desse contrato — o que for peculiar a uma família (um total numérico, um código de fluxograma percorrido) vive dentro dos metadados, nunca no nível raiz.

Essa restrição deliberada é o que permite ao front-end renderizar o resultado de qualquer protocolo com um único componente, sem saber se por trás rodou uma árvore ou uma soma. A trilha explicativa é deliberadamente ambígua entre "nó de árvore percorrido" e "parâmetro pontuado" — ambos cabem no mesmo formato (rótulo, valor observado, contribuição, ordem).

Da mesma forma, todo protocolo expõe seus campos de entrada num formato só: uma lista achatada de campos, cada um com um tipo fechado (numérico ou categórico/enumerado), independente de a estrutura interna ser uma árvore ou uma tabela de pesos. O front-end só precisa saber renderizar esses poucos tipos de campo em sequência — protocolo novo no catálogo não exige deploy de front novo.

## A cascata de liberação: instituição decide o quê, profissional decide a ordem

Existem duas tabelas de configuração, com propósitos que não se sobrepõem:

| Tabela | Quem controla | O que decide |
|---|---|---|
| Liberação institucional | Admin | Se o protocolo pode ser usado NESTA empresa — o único portão real |
| Configuração pessoal | Médico/enfermeiro | Preferência de atalho — quais protocolos aparecem em destaque/mais rápido na consulta |

A liberação institucional é o único gate de execução: um protocolo desligado pela empresa não pode ser executado por ninguém, sob nenhuma circunstância. A configuração pessoal **não bloqueia nada** — é puramente conveniência de interface. Um profissional que nunca marcou preferência por um protocolo liberado ainda pode executá-lo normalmente; ele só não aparece em destaque na tela.

Isso significa que a leitura de um protocolo (estudo, pesquisa de campos) e a execução dele passam por checagens diferentes: ler exige só que a empresa tenha liberado; executar exige a mesma coisa, e nada além disso. Nenhuma das duas etapas depende de preferência pessoal.

Existe ainda uma política de obrigatoriedade que a instituição pode impor por protocolo: quando marcada, a preferência pessoal de destaque não pode ser desligada para aquele protocolo específico — mas isso continua sendo só sobre destaque na interface, nunca sobre permissão de uso.

## O ciclo completo, por etapa

1. **Pesquisa** — leitura aberta a qualquer usuário autenticado, sem exigir papel clínico específico. Estudar um protocolo não é usá-lo clinicamente.
2. **Campos disponíveis** — dado o protocolo liberado pela instituição, o sistema devolve a lista de campos que a família de raciocínio daquele protocolo exige, já no formato fechado que o front sabe renderizar.
3. **Preenchimento** — acontece inteiramente no front-end, fora do escopo do back.
4. **Envio** — o profissional (com papel clínico específico, diferente da etapa de pesquisa) envia as respostas associadas a uma coleta clínica já existente.
5. **Validação de schema** — as respostas são cruzadas contra os campos que a estrutura carregada realmente declara. Uma chave desconhecida é rejeitada explicitamente; um campo declarado mas não enviado vira dado ausente, não erro silencioso.
6. **Cálculo** — função pura, sem qualquer acesso a banco: estrutura validada mais respostas validadas produzem o resultado no contrato único.
7. **Persistência da execução** — o resultado é gravado, junto com metadados de auditoria (quem executou, quando, status de completude).
8. **Contexto** — a execução grava referência à versão vigente do protocolo no momento em que rodou, não uma cópia do conteúdo inteiro. Isso garante rastreabilidade (qual exata definição do protocolo produziu aquele resultado) sem duplicar dado versionado a cada chamada.

## Por que a arquitetura resiste a adicionar protocolos

O ponto de decisão de qual família de raciocínio usar é um único registro, alimentado por uma string vinda do banco (o tipo daquele protocolo) — nunca uma cadeia de condicionais espalhada pelo código. Adicionar uma família nova de raciocínio (a próxima depois de árvore e soma ponderada) é: uma tabela de configuração nova para o conteúdo específico daquela família, uma implementação nova da interface comum, e uma entrada nova nesse registro. Nenhuma família existente é tocada; o orquestrador genérico que resolve permissão, busca a versão vigente e persiste a execução nunca precisa saber qual família está rodando por trás — ele só conhece a interface comum.

Um protocolo que combine mais de uma forma de raciocínio (um funil de elegibilidade que desemboca numa tabela de conduta, por exemplo) é suportável como uma implementação que internamente delega a outras — isso é invisível para tudo que vem antes e depois dela na cadeia.