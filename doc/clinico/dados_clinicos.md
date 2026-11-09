# Dados Clínicos — Sinais vitais, coleta, input de protocolo, execução e envio à IA

Documentação do módulo de registro de dados clínicos durante um Atendimento: sinais vitais, coleta clínica, input de protocolo, execução de protocolo sobre o input vigente e envio do input à IA. O ciclo de vida do atendimento está em `atendimento.md`, o binário em `binario.md` e o fluxo completo em `atendimento_fluxo.md`.

---

# Contexto e conceitos

## Guard de escrita e binário

Toda escrita passa pela checagem comum de escrita clínica (ver `atendimento.md`): atendimento em andamento do **próprio profissional**, do mesmo paciente, enfermeiro só em triagem, paciente sem óbito. A empresa (tenant) vem dessa checagem.

| Registro | Exige binário completo |
|---|---|
| Sinais vitais | Não |
| Coleta clínica | Sim (409) |
| Input de protocolo | Sim (409) |
| Execução de protocolo | Sim (409) |
| Envio à IA | Sim (409) |

## Tipos de atendimento com protocolo

Input de protocolo, execução de protocolo e envio à IA só existem em `triagem`, `avaliacao-medica` e `reavaliacao`. Nos demais tipos (alta e procedimento) o resultado é 409. Esta lista deve andar junto com a do pacote de IA.

---

# Sinais vitais

Corpo: `{"sinais": [ ... ]}`, de 1 a 50 itens. Tudo ou nada: **um sinal inválido derruba o lote inteiro**, que é validado por inteiro antes de gravar e entra num único commit.

| Campo | Regra |
|---|---|
| `tipo_parametro` | Um de `frequencia-respiratoria`, `spo2`, `pa-sistolica`, `pa-diastolica`, `frequencia-cardiaca`, `temperatura`, `glicemia-capilar` |
| `valor_numerico` | Número de 0 a 99999999.99; booleano, NaN e infinito são recusados |
| `unidade` | Precisa corresponder ao tipo: `irpm`, `%`, `mmHg`, `bpm`, `°C` ou `mg-dL` |
| `sitio_medicao` | Opcional: `axilar`, `oral`, `retal`, `timpanico`, `oximetria-digital`, `manguito-braco-direito` ou `manguito-braco-esquerdo` |
| `flag_validacao_faixa` | Padrão `dentro-do-limite`; também `fora-limite-alertado` e `fora-limite-rejeitado` |
| `flag_escala_dpoc` | Padrão `false` |

| Tipo | Unidade esperada |
|---|---|
| `frequencia-respiratoria` | `irpm` |
| `spo2` | `%` |
| `pa-sistolica`, `pa-diastolica` | `mmHg` |
| `frequencia-cardiaca` | `bpm` |
| `temperatura` | `°C` |
| `glicemia-capilar` | `mg-dL` |

Campos extras são recusados. O tipo de parâmetro também precisa existir na tabela de referência LOINC (422 se não existir). A data/hora da medição é a do servidor (UTC) e o `coletado_por` é o usuário da sessão.

---

# Coleta clínica

Corpo: `desde_quando_sintomas` (horas), opcional, inteiro de 0 a 32767. Cria a coleta no atendimento. Exige o binário completo.

---

# Input de protocolo

O cliente manda só o que é **dele**: as respostas ao protocolo, a queixa e o AVPU. O contexto clínico do paciente (binário, dados do paciente, sinais vitais) **não vem do cliente**: o servidor o monta e o congela no envio à IA.

| Campo | Regra |
|---|---|
| `tipo_input` | Opcional. Padrão: o tipo do próprio atendimento; se vier, tem de ser igual (422) |
| `input_json` | Objeto livre, as respostas do protocolo (ainda não há schema por protocolo). A queixa tem campo próprio |
| `queixa_principal` | Texto de até 2000 caracteres |
| `valor_avpu` | Texto de até 20 caracteres |

Textos têm as pontas aparadas, e texto vazio vira ausente. É preciso informar ao menos um de `input_json`, `queixa_principal` e `valor_avpu` (422). Campos extras são recusados.

- A **coleta** informada na rota precisa ser do atendimento (senão 404, sem distinguir "não existe" de "é de outro atendimento").
- **Insert-only:** reenviar cria outro input, e o **último** (maior id) é o vigente.
- Os `dados_criticos_ausentes` são do sistema, preenchidos pela execução, nunca pelo cliente.
- O input de protocolo é parte do domínio Protocolo/IA, fora do escopo FHIR.

---

# Protocolos disponíveis e estrutura

## Disponíveis

O catálogo que passa nos mesmos gates da execução, para o select do front: protocolo **ativo**, de **escopo de uso compatível** com o tipo do atendimento e **liberado pela empresa** (`EmpresaProtocolo.ativo`).

| Tipo de atendimento | Escopo de uso aceito |
|---|---|
| `triagem` | `triagem` |
| `avaliacao-medica` | `consulta` |
| `reavaliacao` | `consulta` |

Protocolos com escopo `ambos` ou sem escopo definido servem a qualquer tipo.

Cada item traz os dados do catálogo mais o resumo da página de catálogo: `liberado_pela_empresa`, `politica`, `padrao_institucional`, `favorito` e `default_pessoal`. Os **favoritos vêm primeiro**, preservando a ordem do catálogo dentro de cada grupo.

## Estrutura

Os campos esperados do protocolo, para o front montar o formulário do input. Passa pelos mesmos gates de uso e reaproveita o caminho das rotas de campos de cada família.

| Campo da resposta | Conteúdo |
|---|---|
| `uuid`, `nome_protocolo`, `sigla` | Identificação |
| `tipo_resultado`, `explicacao_json` | Tipo de resultado e explicação do protocolo |
| `campos` | Lista de `{ campo, texto, label, tipo_campo, opcoes, obrigatorio }` |

`label` é um alias de `texto`. `tipo_campo` é `numero`, `enum` ou `booleano`; `opcoes` é `{valor, rotulo}` para `enum`.

---

# Execução de protocolo

Executa o protocolo, de forma determinística, sobre o **input vigente** do atendimento.

## Guardas (nesta ordem)

1. Guard de escrita (404/409/403).
2. Tipo de atendimento com protocolo (409).
3. Binário completo (409).
4. Protocolo existe (404), está ativo (409), tem escopo compatível (409) e está liberado pela empresa (409). `EmpresaProtocolo.ativo` é o único gate real; a preferência pessoal não bloqueia.
5. Tipo de protocolo com execução disponível (409).
6. Input vigente existe (409).

## Respostas usadas

As respostas vêm de `InputProtocolo.input_json`, **filtradas pelos campos que o protocolo declara**: chave de outro protocolo no mesmo input não derruba a execução. `null` e texto vazio são tratados como não respondidos e viram dado ausente.

Os campos declarados como `booleano` são traduzidos antes da validação:

| Valor recebido | Resultado |
|---|---|
| `true`, `"true"`, `"sim"`, `"s"`, `"yes"`, `"y"`, `"1"`, `"verdadeiro"`, `1` | `true` |
| `false`, `"false"`, `"nao"`, `"n"`, `"no"`, `"0"`, `"falso"`, `0` | `false` |
| Qualquer outra coisa | Volta intacta; a validação do protocolo rejeita (422) |

A comparação ignora acentos e caixa.

## Idempotência

Repetir o **mesmo protocolo no mesmo input** não é erro: devolve a **execução que já existe**, sem recalcular (resposta 200). A checagem é feita com o atendimento travado, então duas requisições simultâneas não violam a UNIQUE. Para executar de novo com respostas diferentes, o médico registra outro input.

## Efeito

Uma execução nova grava o resultado e preenche `InputProtocolo.dados_criticos_ausentes_json` com os dados ausentes **consolidados de todas as execuções do input** (únicos, em ordem estável), tudo em **uma transação**. Qualquer falha desfaz tudo.

---

# Envio à IA

Congela o que a IA vai receber e cria o registro do envio (`OutputBion`). Não há rota própria neste módulo: o serviço é chamado pelo fluxo de avaliação da IA.

Abrir o envio:

1. Guard de escrita.
2. Tipo de atendimento com protocolo (409).
3. Binário completo (409).
4. Existe um input de protocolo no atendimento (409); o vigente é o de maior id.
5. Numa única transação: trava o atendimento, **reconcilia o binário** com os registros ativos, monta o `InputModel` e **grava o `OutputBion`** com o snapshot, ainda sem resposta.

A chamada à IA acontece **depois**, fora deste serviço, e a resposta entra por uma gravação separada (resposta, versão do modelo, índices de completude e confiança). O snapshot enviado nunca muda.

**O que é congelado** (`input_ia_json`): binário (negado ≠ não coletado), dados clínicos ativos, sinais vitais, coleta, queixa, protocolos e lacunas. Não se remonta depois, porque a alergia muda no lugar, o código dos blocos evolui e o binário é reconciliado.

**Vigente:** só o último `OutputBion` do atendimento vale; os anteriores ficam. Envio sem resposta (`output_ia_json` nulo) significa falha ou em andamento, e o que foi enviado fica registrado.

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `controller.py` | Rotas (blueprint `dados_clinicos`) |
| `service.py` | Registro de sinais vitais, coleta e input de protocolo |
| `repository.py` | Acesso a dados de coleta, sinais, input de protocolo e envio à IA |
| `schema.py` | Schemas de entrada |
| `execucao_atendimento_service.py` | Execução de protocolo, protocolos disponíveis e estrutura |
| `envio_ia_service.py` | Abertura do envio à IA e gravação da resposta |
