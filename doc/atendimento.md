# Atendimento — Ciclo de vida

Documentação do módulo de Atendimento: abertura (triagem, avaliação médica e reavaliação), finalização, cancelamento, checagem comum de escrita clínica, detalhe do atendimento e agregações estatísticas. O binário e a conduta de enfermagem são módulos próprios, documentados à parte (`binario.md` e `conduta_enfermagem.md`).

---

# Contexto e conceitos

## Visão geral

A **Consulta** é o episódio de um problema de saúde. Os **Atendimentos** são as etapas dentro dela (1:N). Retornos pelo mesmo problema entram na mesma Consulta. Não há ordem obrigatória entre as etapas: pode haver triagem sem avaliação, avaliação sem triagem (clínica sem enfermeiro) e qualquer tipo pode se repetir.

A única restrição de fluxo é **um Atendimento em andamento por vez** na Consulta, porque o `status_consulta` é derivado do último Atendimento.

## Tipos e status

| Tipo (`tipo_atendimento`) | Quem abre | Quem finaliza |
|---|---|---|
| `triagem` | Enfermeiro ou médico | Quem abriu (enfermeiro ou médico) |
| `avaliacao-medica` | Médico | Quem abriu, desde que médico |
| `reavaliacao` | Médico | Quem abriu, desde que médico |

| Status | Significa |
|---|---|
| `em-andamento` | Aberto; aceita registro de dados clínicos |
| `finalizado` | Concluído; o binário dele vira referência para os próximos atendimentos do paciente |
| `cancelado` | Abandonado (aberto por engano, paciente saiu...). Nunca vira finalizado |

## Posse (tenant) e dono

- O Atendimento **não tem empresa própria**: a posse vem da Consulta (`Consulta.id_empresa`). Toda busca filtra pela empresa da sessão, e "não existe" e "é de outra empresa" dão o mesmo **404**.
- Um Atendimento tem o mesmo profissional do início ao fim. **Só quem o abriu** finaliza ou cancela (403) e escreve dados clínicos nele.

## Abertura

Os três tipos usam o mesmo caminho: busca a Consulta da empresa, **trava a linha da Consulta** (`SELECT ... FOR UPDATE`) e valida. A trava garante que duas aberturas simultâneas não criem dois atendimentos em andamento; ela cai no commit ou no rollback.

Validações, nesta ordem:

| Regra | Erro |
|---|---|
| Consulta não está encerrada (inclusive por evasão) | 409 |
| Consentimento LGPD válido (ativo, ou dispensado por emergência nesta consulta) | 409 |
| Nenhum outro Atendimento em andamento na Consulta | 409 |
| Só reavaliação: Consulta no status de reavaliação (hoje `em-observacao`: atendimento concluído, Consulta ainda aberta) | 409 |

Criar o Atendimento, **derivar o binário a partir do paciente** e recalcular o status da Consulta acontecem num **único commit**.

## Finalização

Só o dono finaliza (403). Avaliação médica e reavaliação só são finalizadas por médico (403 para enfermeiro). Validações:

| Regra | Erro |
|---|---|
| Atendimento não está já finalizado nem cancelado | 409 |
| Consulta não está encerrada | 409 |
| **Binário completo** (as 4 seções conferidas neste atendimento), em qualquer tipo | 409 |
| Sem avaliação da IA em andamento (`processando` dentro do TTL) | 409 |
| Sem prescrição em rascunho (confirmar ou descartar antes) | 409 |
| `observacoes`, se enviadas, são texto | 422 |

Uma avaliação da IA `processando` que já passou do TTL é tarefa perdida e **não bloqueia**.

Na mesma transação: trava o atendimento, **reconcilia o binário** com os registros ativos do paciente (dado inserido depois pela rota granular), grava `status = finalizado`, `data_hora_fim` e `observacoes_profissional`, e sincroniza o status da Consulta.

## Cancelamento

Só o dono (403), só em `em-andamento` (409). **Não exige binário** nem reconcilia: abandonar o atendimento não pode depender de preencher dados. O motivo é opcional; se vier, precisa ser um destes (422 caso contrário):

| `motivo_cancelamento` |
|---|
| `erro-abertura` |
| `paciente-nao-compareceu` |
| `paciente-recusou` |
| `transferencia` |
| `outro` |

Os dados clínicos já gravados no atendimento **permanecem** (nada é apagado). Um rascunho de prescrição que sobrar pode ser descartado depois.

## Binário na abertura

Ao abrir, o binário é derivado do paciente: a seção **consistente** com a última conferência é repassada como `automatico`; a seção cujo dado **mudou** desde então fica `requer-revisao` e trava a finalização até ser confirmada. Detalhes em `binario.md`.

## Checagem comum de escrita clínica

Toda escrita de dado clínico do paciente dentro de um Atendimento (alergia, reação, doença crônica, medicamento, tipo sanguíneo, binário, conduta de enfermagem, coleta e input de protocolo) passa por `ContextoClinicoService.exigir_escrita`, para a regra viver num ponto só. O controller monta o `AutorClinico` (usuário, função e empresa da sessão, nunca do corpo); o service nunca lê a sessão.

| # | Checagem | Erro |
|---|---|---|
| 1 | Atendimento existe na empresa do usuário | 404 |
| 2 | Paciente do caminho existe na empresa | 404 |
| 3 | Paciente do caminho é o mesmo do Atendimento (a tela do paciente errado falha em vez de gravar no errado) | 409 |
| 4 | Quem escreve é o profissional que abriu o Atendimento | 403 |
| 5 | Enfermeiro só escreve em triagem; médico, em qualquer tipo | 403 |
| 6 | Atendimento está `em-andamento` | 409 |
| 7 | Paciente pode receber atendimento (sem óbito) | 409 |

A permissão (403) vem **antes** do estado (409): quem não tem direito não descobre em que estado o Atendimento está.

## Detalhe do atendimento

`GET /<uuid>` devolve o Atendimento com o bloco `paciente` e os campos de **continuidade** (`pode_continuar`, `proxima_acao`, `motivo_bloqueio`).

`GET /<uuid>/detalhe` devolve o resumo completo, em JSON pronto para exibir. É a **mesma fonte do PDF detalhado**, com os mesmos rótulos, então a página e o PDF não divergem.

| Campo | Conteúdo |
|---|---|
| `uuid`, `consulta_uuid`, `tipo`, `tipo_rotulo` | Identificação |
| `status`, `status_rotulo`, `parcial` | Estado; `parcial` é `true` enquanto em andamento |
| `motivo_cancelamento` | Texto do motivo, só quando cancelado |
| `inicio_texto`, `fim_texto`, `duracao_texto` | Datas como **texto** formatado no fuso da empresa |
| `paciente` | `nome`, `identificado`, `idade`, `sexo`, `peso`, `altura` (sem CPF e sem nascimento) |
| `profissional` | `nome`, `funcao`, `registro` |
| `queixa` | `principal`, `sintomas_ha_horas`, `avpu` |
| `sinais_resumo`, `sinais` | Última medição de cada sinal e histórico completo |
| `binario` | Por seção: `estado`, `origem`, `itens` vigentes |
| `protocolo` | `respostas`, `versoes_anteriores_input` e `execucoes` (com `trilha` e `dados_ausentes`) |
| `condutas` | Condutas de enfermagem do atendimento |
| `ia` | Envios à IA (status, modelo, completude, confiança, perguntas) |
| `resultados` | Prescrições e resultados, com medicamentos e exames |
| `observacoes`, `habitos` | Observações do profissional e hábitos do paciente |
| `e_meu` | O atendimento é do usuário logado (o front só mostra o atalho da prescrição ao dono) |

Regras do detalhe: valores livres viram texto (o front usa só `textContent`), `Decimal` vira `float`, e o acesso é o mesmo do PDF (enfermeiro e médico da empresa; **não** exige ser o dono). A leitura é **auditada**.

## Linha do tempo da Consulta

`GET /consulta/<uuid_consulta>` lista os Atendimentos em ordem cronológica, cada um com `profissional` (`uuid`, `nome_completo`, `funcao_clinica` atual). A posse é checada na Consulta.

## Estatísticas

O repository concentra as agregações usadas pela camada de estatística; o service apenas as repassa. Todas filtram pela **empresa da Consulta** (um dado que não muda) e, na segmentada, até a classificação "mesmo profissional x transferência" é calculada só com as Consultas da empresa, para que dados de empresas diferentes não se misturem.

| Método do service | O que devolve |
|---|---|
| `tempo_medio_por_tipo` | Duração média (segundos) dos atendimentos finalizados por tipo, nos últimos N dias |
| `tempo_medio_por_tipo_periodo` | Mesma agregação com janela `[inicio, fim)`, para comparar dois períodos sem sobreposição |
| `tempo_medio_por_tipo_segmentado` | Tempo médio de triagem e avaliação médica, separado em `mesmo_profissional` x `transferencia` |
| `atendimentos_por_status` | Contagem por status nos últimos N dias |
| `media_horas_ate_atendimento` | Média, em horas, entre o início dos sintomas e a busca por atendimento |

A conversão para texto ("8min32s") e a variação percentual contra o período anterior ficam na camada de estatística.

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `controller.py` | Rotas do ciclo de vida (blueprint `atendimento`) |
| `service.py` | Regras de abertura, finalização, cancelamento e consultas |
| `repository.py` | Acesso a dados, trava de linha e agregações estatísticas |
| `contexto_clinico_service.py` | Checagem comum de escrita clínica e `AutorClinico` |
| `detalhe_atendimento_service.py` | JSON do detalhe (provisório, ao lado do serviço de download) |
| `binario/` | Módulo do binário |
| `conduta_enfermagem/` | Módulo da conduta de enfermagem |
