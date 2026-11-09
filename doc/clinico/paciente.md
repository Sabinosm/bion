# Paciente — Cadastro, dados pessoais, status, óbito e prontuário

Documentação do módulo central do domínio: o `Paciente` e os seus dados pessoais (`PacienteDadosPessoais`). Os dados clínicos têm módulos próprios: alergias (`alergia.md`), doenças crônicas (`doenca_cronica.md`), medicamentos em uso (`medicamento_em_uso.md`), tipo sanguíneo (`tipo_sanguineo.md`) e consentimento LGPD (`consentimento.md`). O fluxo completo está em `paciente_fluxo.md`.

---

# Contexto e conceitos

## Visão geral

O paciente é separado em dois registros: o **Paciente** (sexo biológico, nascimento, status, região, bairro, óbito) e os **dados pessoais** (nome, CPF, contatos, endereço), que ficam **cifrados**. Essa separação permite atender sem identificar (emergência) e anonimizar (LGPD) mantendo o histórico clínico.

## Situações do cadastro

| Situação | Como se reconhece | Tem dados pessoais |
|---|---|---|
| Identificado | `nao_identificado = false` e dados pessoais presentes | Sim |
| Não identificado (emergência) | `nao_identificado = true` | Não |
| Anonimizado (LGPD) | Não tem dados pessoais, mas já teve | Não |

"Anonimizado" e "não identificado" não são a mesma coisa: o primeiro já teve dados pessoais e os perdeu; o segundo ainda não os teve.

## Status

| `status` | Significa |
|---|---|
| `ativo` | Em acompanhamento |
| `inativo` | Acompanhamento encerrado |
| `obito` | Óbito registrado (junto de `falecido = true` e `data_obito`) |

Há três eixos independentes: **corrigir o cadastro** é gestão de dados e nunca escreve campo clínico; o **status clínico** só alterna entre `ativo` e `inativo`; e o **óbito** só muda por registrar e reverter, que mantêm `status`, `falecido` e `data_obito` sempre sincronizados.

## Isolamento entre empresas

Toda busca por UUID, por CPF e toda listagem **filtram pela empresa da sessão**, dentro do repository. "Não existe" e "é de outra empresa" dão o mesmo **404**. O mesmo CPF pode existir como pacientes distintos em empresas diferentes (a pessoa é atendida em clínicas diferentes), e a unicidade é **por empresa**.

## Proteção da PII

Nome, CPF, telefone, e-mail, logradouro, CEP e telefone de emergência são **cifrados** (AES). O CPF também tem um **hash** (HMAC) para busca exata sem descriptografar. Descriptografar é acesso a PII, então fica centralizado no service e o controller só pede quando o usuário pode ver.

---

# Cadastro

## Cadastro completo

Grava o `Paciente` e os dados pessoais numa **única transação** (uma falha no segundo não deixa paciente órfão).

| Campo | Regra |
|---|---|
| `sexo_biologico` | Obrigatório: `M`, `F` ou `I` |
| `data_nascimento` | Obrigatório; não pode ser futura |
| `nome_completo` | Obrigatório; até 500 caracteres; não pode ser só espaços |
| `cpf` | Obrigatório; validado com dígito verificador |
| `telefone`, `contato_emergencia_telefone` | Opcionais; telefone brasileiro válido (DDD e formato) |
| `email` | Opcional; e-mail válido |
| `logradouro` | Opcional; até 500 caracteres |
| `cep` | Opcional; 8 dígitos reais (sequências como `11111111` são recusadas); normalizado para só dígitos |
| `numero_residencia`, `rg`, `contato_emergencia_nome` | Opcionais; vazio vira ausente |
| `bairro` | Opcional; tem **prioridade** sobre o bairro resolvido pelo CEP |
| `data_primeiro_atendimento` | Opcional; não pode ser futura; padrão: hoje |

Regras: a **região geográfica é sempre derivada do CEP**, nunca aceita do corpo; sem CEP a região fica vazia; com CEP cuja região não é resolvida, o cadastro **inteiro falha** (422). O bairro do corpo tem prioridade e só cai no bairro do CEP se vier ausente. O tipo sanguíneo **não** entra no cadastro: é dado clínico, registrado dentro de um atendimento. Status, falecido e óbito também não entram (o cadastro nasce com os padrões do model).

| Regra | Erro |
|---|---|
| Corpo inválido (erros por campo) | 422 |
| CEP sem região resolvida | 422 |
| CPF já cadastrado **nesta empresa** (inclusive em corrida, barrada pela UNIQUE composta) | 409 |

## Cadastro de emergência (não identificado)

Cria um `Paciente` mínimo, **sem dados pessoais**, marcado `nao_identificado = true`, com o sexo biológico informado (`M`, `F` ou `I`; 422 caso contrário). É usado na abertura de consulta de emergência (SAMU, paciente inconsciente), não tem rota própria.

## Identificar

Completa um paciente de emergência com os dados do cadastro (mesmo corpo do cadastro completo), **sem criar um segundo paciente**: consulta, consentimento e atendimento já gravados ficam no mesmo registro. A data do primeiro atendimento **não** é sobrescrita.

| Regra | Erro |
|---|---|
| Paciente existe na empresa | 404 |
| Paciente **não** está falecido (identificar é fluxo clínico de quem está sendo atendido) | 409 |
| Paciente ainda **não identificado** | 409 |
| CPF novo ainda não cadastrado na empresa | 409 |
| Corpo inválido ou CEP sem região | 422 |

---

# Atualização

## Dados pessoais

Corrige o cadastro, **só os campos enviados**. Aceita os campos de nome, telefone, e-mail, logradouro, CEP, contato de emergência, RG e número da residência, com as mesmas validações do cadastro. Campo opcional enviado como `null` é **limpo** (telefone, e-mail, número da residência, RG, nome e telefone de emergência). O schema nunca aceita `status`.

| Regra | Erro |
|---|---|
| Paciente existe na empresa | 404 |
| Paciente tem dados pessoais (não é não identificado nem anonimizado) | 422 |
| Corpo inválido | 422 |
| CEP novo sem região resolvida | 422 |

**Trocar o CEP recalcula a região geográfica e o bairro** do paciente (a região é sempre derivada do CEP). O bairro só é trocado se o CEP novo o resolver; se não resolver, o anterior fica. Se o CEP novo não resolve a região, a atualização inteira falha (422), como no cadastro, e nada é alterado.

Corrigir cadastro de falecido é legítimo: não há bloqueio por óbito.

## Status clínico

Altera apenas `status`, entre `ativo` e `inativo`. O corpo rejeita campos fora do contrato (422), em especial `falecido`, `data_obito` e `status = "obito"`. Paciente com óbito registrado dá 409 (use reverter o óbito antes).

Quando quem grava é o **admin** (exceção ao fluxo clínico), a alteração e uma linha de **auditoria** são gravadas na mesma transação.

## Óbito

**Registrar** o óbito mantém `status = "obito"`, `falecido = true` e `data_obito` sincronizados (é a única via de entrada para esses campos).

| Regra | Erro |
|---|---|
| `data_obito` informada (`AAAA-MM-DD`) | 422 |
| Não é data futura | 422 |
| Não é anterior ao nascimento | 422 |
| Paciente ainda não está falecido | 409 |
| Sem **consulta aberta** (encerre-a antes) | 409 |

**Reverter** o óbito (marcado por engano) limpa `falecido` e `data_obito` e devolve o status ao destino informado (`ativo`, padrão, ou `inativo`); o status anterior não é guardado. 409 se o paciente não está com óbito; 422 para destino fora de `ativo` e `inativo`.

## Anonimização (LGPD)

Irreversível: apaga os dados pessoais e mantém o registro clínico anonimizado. A definição do que anonimizar vive no model (`Paciente.anonimizar`). 422 se o paciente é não identificado ou já está anonimizado.

---

# Leitura

## Listagem enxuta (resumo)

Paginada, **8 por página**, do mais recente ao mais antigo, com `nome_completo` e o início do CPF (4 dígitos) descriptografados.

| Filtro | Regra |
|---|---|
| `status`, `sexo_biologico` | Igualdade |
| `q` | CPF completo (11 dígitos): busca exata pelo hash. Texto: parte do nome, sem acento nem caixa, **em memória** (o nome é cifrado). CPF parcial não é pesquisável |

## Visibilidade da PII

| Resposta | PII em texto claro |
|---|---|
| Lista geral | Só para médico e enfermeiro |
| Detalhe pessoal, cadastro, identificação e correção | Sempre (as rotas já restringem os papéis) |
| Listagem enxuta | Nome e 4 dígitos do CPF |
| Prontuário clínico | Nunca (só dado clínico) |

## Contagens

Pacientes cadastrados **hoje**, no fuso da empresa (o `criado_em` é UTC, então o dia é calculado no fuso local e convertido), e total de pacientes da empresa.

## Prontuário clínico completo

Usado **só** na tela de detalhe, nunca em listagem (cada domínio é uma consulta própria). O paciente é carregado **uma vez** e passado aos services clínicos, que têm métodos para paciente já carregado, em vez de cada um refazer a busca por UUID; as interações são calculadas sobre a lista de medicamentos já lida. Acrescenta ao paciente:

| Campo | Conteúdo |
|---|---|
| `tipo_sanguineo` | Valor vigente (texto) ou `null` |
| `tipo_sanguineo_vigente` | Observação completa ou `null` |
| `resumo_clinico` | Bloco de alerta do topo (ver abaixo) |
| `alergias` | Grave primeiro (não por ordem de cadastro) |
| `doencas_cronicas` | Doenças vigentes |
| `medicamentos_em_uso` | Ativos primeiro; encerrados como histórico |
| `interacoes_medicamentosas` | Interações entre os ativos, com `cobertura` (lista vazia não prova ausência de interação) |
| `consentimento_ativo` | Booleano; o consentimento é titularidade/LGPD, não dado clínico |

O `resumo_clinico` é calculado na hora, das mesmas listas, para leitura rápida em emergência:

| Parte | Conteúdo |
|---|---|
| `tipo_sanguineo` | `registrado` (nunca coletado ou não), `valor`, `conhecido` (falso se `desconhecido`), `registrado_em` |
| `alergias` | `total`, `tem_grave`, `resumo` (substância e gravidade) |
| `doencas_cronicas` | `total`, `ativas`, `resumo` das ativas |
| `medicamentos_em_uso` | `total`, `em_uso_continuo`, `resumo`, `nao_verificaveis_interacao` (ativos sem vínculo com o catálogo) e `interacoes_encontradas` |

---

# Transação

O service **não toca em `db.session`**: todo commit, flush e rollback é do repository. Os métodos de escrita aceitam `commit`: com `True` (padrão) a operação confirma sozinha e desfaz sozinha em caso de erro; com `False` fica pendente (flush) para o chamador comitar junto com outras escritas (abrir consulta com cadastro e consentimento, ou uma ação sensível com a alteração e o log). Com `commit=False`, o rollback é de quem controla a transação.

Paciente **nunca é apagado fisicamente** (o prontuário e as consultas dependem dele): para LGPD use a anonimização; para encerrar o acompanhamento, `status = inativo`.

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `controllers/paciente_pessoal_controller.py` | Rotas de cadastro e dados pessoais |
| `controllers/paciente_clinico_controller.py` | Rotas de prontuário, status e óbito |
| `services/paciente_service/` | Service por responsabilidade: `leitura.py`, `cadastro.py`, `atualizacao.py`, `helpers.py`, montados em `service.py` |
| `services/montar_prontuario_service.py` | Composição do prontuário completo |
| `repositories/paciente_repository.py` | Acesso a dados, isolamento por empresa, contagens e auditoria |
| `schemas/schema_paciente.py` | Schemas de entrada (criação, atualização pessoal e clínica) |
| `services/comum.py` e `controllers/comum.py` | Utilitários compartilhados pelos módulos do domínio |
