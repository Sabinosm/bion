# Binário — Conferência das quatro seções clínicas

Documentação do módulo do binário: a conferência, dentro de um Atendimento, das quatro seções clínicas do paciente (alergias, medicamentos, tipo sanguíneo e doença crônica). O ciclo de vida do atendimento está em `atendimento.md`.

---

# Contexto e conceitos

## Visão geral

O binário responde, para cada seção, a pergunta "o paciente tem este dado?". O profissional **confere** cada seção no atendimento: confirma o que já existe, registra itens novos, nega ("não possui") ou declara que não foi possível coletar. Enquanto alguma seção estiver pendente, o binário está **incompleto** e o atendimento **não pode ser finalizado**; o mesmo gate vale para a coleta clínica, o input de protocolo e o envio à IA.

Seções (`secao`): `alergias`, `medicamentos`, `tipo_sanguineo`, `doenca_cronica`.

## Estado: onde vive

Não existe tabela de estado. Ele vive na coluna JSON `binario` do Atendimento, lida e escrita pelo objeto `Binario`. O gate recebe o objeto Atendimento, então não faz consulta extra ao banco.

## Estados de uma seção

| Estado | Significa | Conta como conferida |
|---|---|---|
| `preenchido` | O paciente tem o dado (itens no payload ou registro ativo já existente, só confirmado) | Sim |
| `nega` | O paciente não possui o dado | Sim |
| `nao-coletado` | Não foi possível coletar (aparece como "não registrado") | Sim |
| `pendente` | Ainda não conferida | Não |
| `requer-revisao` | Veio derivada de uma conferência anterior, mas o dado mudou desde então; é preciso confirmar | Não (conta como pendente) |

A **origem** de uma seção conferida é `manual` (confirmada pelo profissional) ou `automatico` (derivada do cadastro do paciente). Uma seção conferida como `nega` ou `nao-coletado` que depois ganha registro ativo é marcada como `reconciliado` e passa a `preenchido`.

## Regras de cada seção

| Entrada | Efeito |
|---|---|
| `possui=true` com itens | Cria os itens e a seção fica `preenchido` |
| `possui=true` sem itens | Só vale se já existe registro ativo (confirmação do pré-preenchido); senão **422** |
| `possui=false` | Seção `nega`. Se há registro ativo, **409**: remova antes o registro (exclusão lógica) |
| `nao_foi_possivel_coletar=true` | Seção `nao-coletado`; força `possui=false` e não aceita itens |
| Itens com `possui=false` | **422** |
| Tipo sanguíneo com `possui=false` | **422**: todo paciente tem tipo sanguíneo; registre `desconhecido` ou use `nao_foi_possivel_coletar` |
| Reconferir a mesma seção no mesmo atendimento | **409** |

Os itens são dicts validados pelos schemas dos próprios dados clínicos (alergia, medicamento em uso, doença crônica e tipo sanguíneo): existe uma só fonte de validação, e o binário chama o **service público** de cada dado, com o mesmo guard das rotas granulares do dado. No máximo 50 itens por seção.

No **tipo sanguíneo**, `tipo_sanguineo` informado só registra uma nova observação se for diferente do vigente; igual ao vigente é apenas confirmação.

## Transação e concorrência

A rota agregada e a granular usam o mesmo caminho por seção, com os services dos dados em **commit desligado**. Há **um único commit** no fim; qualquer falha desfaz tudo (o lote agregado é tudo ou nada). Como a conferência lê, altera e grava um JSON, a linha do atendimento é **travada** (`SELECT ... FOR UPDATE`) antes de ler o binário, para duas requisições simultâneas não se sobrescreverem. Um `IntegrityError` vira 409 ("registro duplicado").

## Guard de escrita

Toda escrita passa pela checagem comum de escrita clínica (ver `atendimento.md`): atendimento em andamento do próprio profissional, mesmo paciente, enfermeiro só em triagem e paciente sem óbito. A **leitura** é de médico ou enfermeiro da empresa (o atendimento é buscado pela empresa da sessão, com 404 uniforme).

## Pré-preenchimento (estado)

`GET /<uuid_atendimento>/binario` mostra o estado de cada seção. Seção **conferida** devolve o que foi conferido. Seção **pendente** devolve os registros ativos do paciente em `pre_preenchido`; cada item traz `de_outro_atendimento` (veio de outro momento e precisa de confirmação visual), e a seção traz `precisa_confirmacao`. Seção `requer-revisao` traz também `origem = "automatico"`, `requer_revisao = true` e o motivo da revisão: o front desmarca a seção e bloqueia o avanço até confirmar.

| Campo da resposta | Conteúdo |
|---|---|
| `uuid_atendimento` | Atendimento |
| `completo` | `true` se não há seção pendente |
| `pendentes` | Seções ainda não conferidas |
| `secoes` | Mapa seção → estado, itens e pré-preenchimento |

## Binário montado a partir do paciente

`GET /<uuid_atendimento>/binario/do-paciente` monta o binário no formato do corpo da rota agregada, **sem gravar nada**. Os registros ativos do paciente são a verdade. Seção sem registro ativo herda `nega` ou `nao-coletado` da **última conferência confirmada** (atendimentos finalizados anteriores); sem histórico, fica pendente (`possui = null`). Tipo sanguíneo nunca herda `nega`.

| Campo da resposta | Conteúdo |
|---|---|
| `binario` | O binário para exibir e editar, com itens |
| `confirmacao` | Seções resolvidas, prontas para o `POST` sem duplicar registros (confirmar o que existe vai **sem itens**) |
| `pendentes` | Seções sem base: o profissional decide |
| `completo` | `true` se `confirmacao` serve na rota agregada |

## Derivação na abertura e reconciliação

- **Derivar na abertura:** quando um Atendimento novo é criado, cada seção é cruzada com a última conferência confirmada do paciente (atendimentos **finalizados** anteriores, até 50). Consistente: repassa como `automatico`. Mudou: `requer-revisao`.
- **Reconciliar:** na finalização e no envio à IA, o binário do atendimento é alinhado com os registros ativos (o profissional conferiu "nega" e depois adicionou uma alergia pela rota granular). Não mexe em seção pendente. O chamador é dono da transação e já travou o atendimento.

## Gate do binário

`exigir_binario_completo(atendimento)` lança **409** com a lista das seções pendentes. O módulo é leve de propósito (só o objeto `Binario` e a exceção), para a finalização, a coleta clínica, o input de protocolo e o envio à IA importarem daqui sem criar ciclo com os services de paciente.

## Resposta de uma conferência

| Campo | Conteúdo |
|---|---|
| `conferidas` | Para cada seção: `secao`, `estado`, `itens_criados` e, em medicamentos, `alertas_interacao` |
| `binario` | O estado completo do binário, como em `GET /<uuid_atendimento>/binario` |

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `binario_controller.py` | Rotas do binário (blueprint `binario`) |
| `binario_service.py` | Conferência, estado, derivação e reconciliação |
| `binario_gate.py` | Gate leve "binário completo" |
| `schema_binario.py` | Schemas de entrada por seção e agregado |
