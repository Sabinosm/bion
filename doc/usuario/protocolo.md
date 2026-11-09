# Protocolo — Catálogo, Execução e Famílias de Cálculo

Domínio responsável pelos protocolos clínicos do Bion: o **catálogo** de protocolos, a **execução** (cálculo + registro do resultado sobre um input de atendimento) e as **famílias de cálculo** que sabem calcular cada tipo de protocolo.

Hoje existem duas famílias:

| `tipo_protocolo` | Família | Exemplo |
|---|---|---|
| `escore-ponderado` | Soma de pontos de parâmetros isolados | NEWS2 |
| `protocolo-composto` | Vários módulos combinados por uma regra de agregação | Protocolos montados a partir de pontuadores, classificadores e regras |

---

## Conceitos

- **Catálogo (`ProtocoloCatalogo`)**: cadastro do protocolo (nome, sigla, tipo, escopo de população e de uso, vigência, referência, explicação).
- **Versão (`ProtocoloVersao`)**: cada protocolo tem uma versão com `status = 'ativa'` (a vigente). A execução sempre registra qual versão foi usada.
- **Liberação institucional (`EmpresaProtocolo`)**: a empresa precisa ter o protocolo `ativo` para que seus profissionais o executem. É o **único gate** de execução.
- **Preferência pessoal (`configuracao_protocolo`)**: favorito e padrão do profissional. **Nunca bloqueia** a execução.
- **Estratégia (Strategy)**: classe de uma família que sabe carregar a configuração, listar campos, validar respostas e calcular.
- **Execução (`InputProtocoloExecucao`)**: resultado gravado de um protocolo sobre um input. Existe **no máximo uma execução por protocolo e por input**.

### Ver não é usar

Consultar um protocolo (detalhe, campos, composição) é aberto a qualquer usuário logado, liberado ou não. Só a **execução** exige liberação da empresa e papel clínico (médico ou enfermeiro).

---

## Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `protocolo_catalogo_controller.py` | Rotas do catálogo; define o blueprint `bp_protocolo` usado por todos os controllers do domínio |
| `shared/services/protocolo_catalogo_service.py` | Cadastro, consultas e montagem dos resumos dos cards |
| `shared/services/protocolo_detalhe_service.py` | Detalhe de um protocolo (protocolo + resumo + versão ativa) |
| `shared/services/execucao_protocolo_service.py` | Orquestrador genérico de execução |
| `shared/repositories/protocolo_catalogo_repository.py` | Consultas do catálogo e listagens com status de liberação |
| `shared/repositories/protocolo_versao_repository.py` | Versão vigente do protocolo |
| `shared/repositories/input_protocolo_execucao_repository.py` | Persistência das execuções |
| `shared/exceptions_protocolo.py` | Exceções de configuração inconsistente (status 500, detalhe no log) |
| `shared/strategy/base.py` | Interface `ProtocoloStrategy` e `CampoEsperado` |
| `shared/strategy/protocolo_factory.py` | Escolhe a estratégia pelo `tipo_protocolo` |
| `shared/strategy/conversao_numerica.py` | Conversão padronizada de respostas numéricas, usada por todas as famílias |
| `shared/schemas/schema_resultado.py` | Contrato de saída comum a todas as famílias |
| `shared/schemas/schema_execucao.py` | Contrato do corpo de execução (`id_input` e `respostas`) e sua validação |
| `shared/schemas/schema_explicacao_protocolo.py` | Explicação obrigatória do protocolo (usada no seed) |
| `news2/` | Família escore ponderado (controller, service, repository, estratégia e schema) |
| `protocolo_composto/` | Família protocolo composto (controller, service, repository, estratégia, avaliadores, logic e schemas) |

---

## Catálogo

### Resumo do card

Cada card da listagem do catálogo tem este formato:

| Campo | Significado |
|---|---|
| `uuid`, `nome_protocolo`, `sigla` | Identificação |
| `tipo_protocolo`, `escopo_populacao`, `escopo_uso` | Classificação do protocolo |
| `liberado_pela_empresa` | `true` se a empresa do usuário liberou o protocolo |
| `politica` | Política definida pela empresa para o protocolo (ou `null`) |
| `padrao_institucional` | Escopo em que o protocolo é o padrão da instituição (trava a estrela cheia) |
| `favorito` | `null` = usuário sem papel clínico; `true`/`false` = favorito do profissional |
| `default_pessoal` | Escopo em que é o padrão pessoal do profissional, ou `null` |

Só **médico** e **enfermeiro** têm favoritos; para os demais, `favorito` e `default_pessoal` saem `null`.

### Listagem e filtros

- A listagem mostra apenas protocolos com `status = 'ativo'`.
- Protocolo que a empresa nunca tocou **aparece** com `liberado_pela_empresa = false`.
- Filtros: `tipo_protocolo`, `escopo_populacao`, `escopo_uso` (casa o valor informado **ou** `ambos`) e `apenas_liberados`.
- Paginação: 20 itens por página, ordenados por ID. Página negativa vale 0.
- Um protocolo atende ao escopo de uso se for o informado, `ambos` ou não definido.

### Detalhe

Devolve `protocolo` (dados do catálogo, `explicacao` com `o_que_e`/`quando_usar`/`como_interpretar` e datas em `AAAA-MM-DD`), `resumo` (mesmo formato do card) e `versao_ativa` (`numero_versao`, `vigente_desde`, `status`, ou `null` se não houver versão ativa).

---

## Execução

Fluxo do orquestrador (`ExecucaoProtocoloService.executar_e_persistir`):

1. Busca o protocolo no catálogo e confere que ele é do tipo da família chamadora e que está `ativo` no catálogo.
2. Verifica se já existe execução para o par input + protocolo (conflito).
3. Busca a **versão vigente** do protocolo.
4. Escolhe a estratégia pelo `tipo_protocolo`.
5. Busca a configuração com o callback da família, recebendo a versão vigente.
6. Carrega a estrutura, valida as respostas e calcula o resultado.
7. Grava a execução com a versão utilizada.

Status da execução gravada:

| Status | Quando |
|---|---|
| `concluida` | Nenhum dado ausente |
| `incompleta` | O resultado tem `dados_ausentes` |

### Rotas por família

Cada família só atende protocolos do seu `tipo_protocolo`. Consultar ou executar um protocolo pela rota de outra família é rejeitado como dado inválido. Todas as rotas identificam o protocolo pelo **UUID** do catálogo.

### Campos que o front renderiza

Todas as famílias devolvem os campos no mesmo formato (`CampoEsperado`):

| Campo | Conteúdo |
|---|---|
| `campo` | Código do campo, usado como chave em `respostas` |
| `texto` | Rótulo exibido |
| `tipo_campo` | `numero`, `enum` ou `booleano` |
| `opcoes` | Só para `enum`: lista de `{ "valor", "rotulo" }`; `null` nos demais |

### Contrato de saída (`SchemaResultado`)

| Campo | Conteúdo |
|---|---|
| `classificacao` | Categoria final |
| `trilha_explicativa` | Lista de passos (`rotulo`, `valor_observado`, `peso_ou_resultado`, `ordem`) |
| `dados_ausentes` | Campos que não foram informados |
| `metadata` | Dados específicos da família |

---

## Família: escore ponderado (NEWS2)

O resultado vem da **soma de pontos** de parâmetros isolados.

### Configuração

| Parte | Descrição |
|---|---|
| `parametros` | Lista de parâmetros. Cada um é `numero` (com `faixas`) ou `enum` (com `opcoes`) |
| `regra_override` | Opcional. Dispara quando **qualquer parâmetro isolado** atinge `pontos_minimos` (NEWS2: 3) |
| `faixas_interpretacao` | Faixas do escore total → categoria e ação recomendada |

- Pontos de cada parâmetro: inteiros não negativos, sem teto. Cada escore define a própria escala (NEWS2 usa de 0 a 3 por parâmetro).
- Faixas numéricas dos parâmetros têm limites **inclusivos** (`valor_min` e `valor_max`); `None` significa aberto.
- Com `regra_override`, é preciso **exatamente uma** faixa marcada `aplicada_por_override`.

### Respostas

- Campo desconhecido é rejeitado.
- `numero`: aceita número ou texto com vírgula decimal; rejeita booleano, NaN e infinito. O valor também precisa caber em alguma faixa do parâmetro; fora das faixas, a resposta é rejeitada como inválida.
- `enum`: o valor precisa ser uma das opções.
- `None` ou texto vazio é tratado como **ausente**.

### Classificação

1. Soma os pontos dos parâmetros respondidos.
2. Se o override disparou e há faixa de override, ela vale **enquanto** `total <= escore_max` dela (ou sem teto). Acima disso, prevalece a faixa normal do total: **o override nunca rebaixa**.
3. Caso contrário, usa a faixa normal que contém o total.

`metadata`: `escore_total`, `override_disparado`, `acao_recomendada`, `escore_parcial` (`true` quando há parâmetros ausentes, pois o total pode estar subestimado).

---

## Família: protocolo composto

O protocolo é formado por **módulos**, cada um com sua família de cálculo, papel e grupo de agregação.

### Família do módulo

| Família | `tipo_saida` | O que faz |
|---|---|---|
| `pontuador` | `pontos` | Soma pontos por parâmetro (por faixa ou por mapeamento) e interpreta o total, inclusive com interpretação segmentada por uma variável de entrada (ex.: sexo biológico) |
| `classificador` | `categoria` | Escolhe UMA categoria por faixas (uma variável) ou por regras (condições sobre várias variáveis, a primeira que casa vence, com saída padrão) |
| `regra` | `flag` | Avalia uma condição e devolve verdadeiro/falso com classificação e motivo |

### Papel do módulo

| Papel | Comportamento |
|---|---|
| `principal` | Módulo normal |
| `gatilho` | Avaliado primeiro; seu resultado pode desligar outros módulos |
| `informativo` | Calculado e exibido, sem peso especial |

Só participam da agregação os módulos com papel diferente de `gatilho` **e** `grupo_agregacao` preenchido; os demais ficam em modo **paralelo**.

### Etapas do cálculo

1. Avalia os módulos `gatilho`.
2. Aplica `regra_gatilho_json`: os módulos desligados ficam `nao_aplicavel`, com o motivo.
3. Avalia os demais módulos.
4. Agrega o grupo.
5. Monta o `SchemaResultado`: trilhas concatenadas e renumeradas, dados ausentes unidos e ordenados.

### Status de cada módulo

| Status | Significado |
|---|---|
| `calculado` | Resultado obtido |
| `nao_calculavel` | Faltou dado obrigatório ou o valor está fora do domínio coberto |
| `nao_aplicavel` | Desligado por um gatilho |

### Regra de gatilho

```json
{
  "gatilhos": [
    {
      "modulo": "<sigla do módulo-gatilho>",
      "quando_classificacao": ["<classificação>"],
      "desliga": ["<sigla>"],
      "motivo": "<texto exibido nos módulos desligados>"
    }
  ]
}
```

Se o módulo-gatilho está `nao_calculavel`, o gatilho **não desliga nada**. Se dois gatilhos desligam o mesmo módulo, vale o primeiro motivo.

### Agregação

| Tipo | Exige `tipo_saida` | Resultado |
|---|---|---|
| `nenhuma` | qualquer | `classificacao = "multiplos-resultados"`; o front exibe `metadata.modulos` em destaque |
| `soma` | `pontos` | `total=<soma>` |
| `maximo` | `pontos` | `maximo=<maior>` (ou `sem_dado`) |
| `pior_categoria` | `categoria` | Categoria de maior `gravidade` (ou `sem_dado`) |
| `any_flag` | `flag` | `alerta` se algum flag é verdadeiro, senão `sem_alerta` |

Módulos `nao_calculavel` e `nao_aplicavel` **nunca entram como zero**: são excluídos e a agregação é marcada como **parcial**, listando `modulos_excluidos` (de todos os grupos).

O tipo de agregação do protocolo vale para **cada grupo**. Com um único grupo, a classificação e o valor finais são os dele. Com mais de um grupo não há resultado combinado: a classificação é `multiplos-resultados`, o `valor` é `null` e o resultado de cada grupo fica em `metadata.agregacao.grupos`.

### Condições (classificador por regras e módulo de regra)

```
condicao   := comparacao | {"e": [condicao...]} | {"ou": [condicao...]} | {"nao": condicao}
comparacao := {"variavel": <codigo>, "op": <op>, "valor": <literal>}
op         := "<" | "<=" | ">" | ">=" | "==" | "!=" | "em" | "nao_em"
```

A lógica tem **três valores** (verdadeiro, falso, desconhecido). Variável ausente resulta em **desconhecido**, nunca em falso, para que um alerta clínico não deixe de disparar em silêncio. Se nenhuma regra do classificador casa, mas alguma ficou desconhecida, o módulo fica `nao_calculavel` em vez de assumir o padrão.

### Faixas

No protocolo composto, a faixa é **`[min, max)`**: mínimo inclusivo, máximo exclusivo. `min = None` é sem piso e `max = None` é sem teto. Cada lista de faixas precisa cobrir o domínio sem buraco nem sobreposição, com exatamente uma faixa de piso aberto e uma de teto aberto.

### Respostas

- Campo desconhecido é rejeitado.
- `numerico`: mesma conversão do escore ponderado (aceita vírgula decimal; rejeita booleano, NaN e infinito) e conferido contra `valor_min`/`valor_max` da variável.
- `categorico`: precisa ser uma das opções.
- `booleano`: precisa ser `true` ou `false`.
- Variável não enviada, `null` ou texto vazio é **dado ausente**, tratado pelos avaliadores.

### `metadata` do resultado

| Campo | Conteúdo |
|---|---|
| `modulos` | Resultado de cada módulo |
| `alertas` | Módulos `flag` calculados com valor verdadeiro (exceto gatilhos) |
| `agregacao` | `tipo`, `valor`, `grupos`, `parcial`, `modulos_excluidos` |
| `codigo_composicao` | Código da composição da versão |

---

## Erros de configuração

Quando o cadastro de um protocolo está inconsistente (estrutura que não passa no schema, família sem estratégia registrada, valor sem faixa de interpretação, agregação incompatível com os módulos, regra de gatilho ou condição malformada), o cálculo lança uma `ConfiguracaoProtocoloInvalidaError` (`EstruturaInvalida`, `AgregacaoInvalida`, `GatilhoInvalido` ou `CondicaoInvalida`): status 500, mensagem segura para o usuário e detalhe no log. Resposta inválida do profissional continua sendo `DadosInvalidosError` (422).

## Como adicionar uma nova família

1. Criar a estratégia implementando `ProtocoloStrategy` (carregar estrutura, campos esperados, validar respostas e executar).
2. Registrá-la em `ProtocoloFactory` com o novo `tipo_protocolo`.
3. Criar o service da família, com a busca da configuração, para passar ao orquestrador como callback (que recebe a versão vigente).
4. Criar o controller da família, registrando as rotas em `bp_protocolo`.

## Como adicionar uma nova família de módulo (protocolo composto)

1. Criar o avaliador da família em `avaliadores/`, como função pura `(ModuloDef, dados) -> ResultadoModulo`.
2. Registrar a função em `AVALIADORES`.
3. Criar o schema de configuração em `schemas/config_schemas.py` e incluí-lo em `validar_configuracao`.
