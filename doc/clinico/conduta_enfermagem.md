# Conduta de Enfermagem

Documentação do módulo de conduta de enfermagem: o registro opcional em que o profissional detalha o que fez durante um Atendimento de **triagem**. O ciclo de vida do atendimento está em `atendimento.md`.

---

# Contexto e conceitos

## Visão geral

A conduta de enfermagem é um texto livre (com vínculo opcional a um protocolo do catálogo) que o profissional registra durante a triagem para documentar o que fez. Ela é **opcional**: **não entra no gate do binário** e **não bloqueia a finalização** do atendimento. Na avaliação, o médico lê as condutas da consulta inteira para saber o que a triagem fez.

## Insert-only

O registro nunca é editado nem apagado. **Corrigir é registrar uma nova conduta.** Por isso o repository não tem atualização e a remoção levanta `NotImplementedError`.

## Regras de escrita

A escrita passa pela checagem comum de escrita clínica (ver `atendimento.md`) e por regras próprias:

| # | Regra | Erro |
|---|---|---|
| 1 | Atendimento existe na empresa do usuário | 404 |
| 2 | Paciente do caminho existe na empresa e é o do Atendimento | 404 / 409 |
| 3 | Só o dono do Atendimento escreve; enfermeiro e médico podem | 403 |
| 4 | Atendimento está `em-andamento` (conferido de novo **depois de travar a linha**, para não gravar numa triagem finalizada no meio da requisição) | 409 |
| 5 | Paciente pode receber atendimento (sem óbito) | 409 |
| 6 | O tipo do Atendimento permite conduta (hoje só `triagem`) | 409 |
| 7 | Se informado, o protocolo do catálogo existe | 422 |

A função de quem escreveu (`medico` ou `enfermeiro`) vem da **sessão** e fica gravada na conduta. Autor, função, atendimento e data nunca vêm do corpo.

## Corpo de entrada

| Campo | Tipo | Regra |
|---|---|---|
| `descricao_conduta` | texto | Obrigatório; de 3 a 2000 caracteres (espaços nas pontas são removidos) |
| `uuid_protocolo_catalogo` | texto | Opcional; UUID de 36 caracteres do protocolo do catálogo que motivou a conduta |

Qualquer outro campo no corpo é recusado.

## Auditoria e transação

A escrita é **auditada** e comita **junto com o log**: o service roda com commit desligado e o decorator de auditoria confirma a transação. O decorator espera o par `(resposta, meta)` mesmo nos retornos de erro; quando nada é gravado (validação ou regra de negócio recusou), a meta é `NOOP`.

## Posse (tenant)

A conduta não tem empresa própria: a posse vem de `Atendimento -> Consulta.id_empresa`, validada no service antes de consultar. Nas listagens, "não existe" e "é de outra empresa" dão o mesmo 404.

## Leitura

| Consulta | Ordem |
|---|---|
| Condutas de um Atendimento | Cronológica crescente |
| Condutas de todos os Atendimentos de uma Consulta | Cronológica crescente |

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `controller.py` | Rotas (blueprint `conduta_enfermagem`) |
| `service.py` | Regras de registro e listagens |
| `repository.py` | Acesso a dados, insert-only |
| `schema.py` | Schema do corpo de entrada |
