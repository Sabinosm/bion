# Fluxo de Empresa e Liberação de Protocolos

Documentação do domínio de empresa (tenant): cadastro da empresa com seu admin fundador, atualização dos dados cadastrais, verificação de identificadores e liberação institucional de protocolos clínicos do catálogo.

---

# Contexto e conceitos

## Visão geral

O domínio cobre dois assuntos que se encadeiam:

1. **Empresa**: a organização cliente (tenant). Nasce junto com o seu admin fundador e mantém dados cadastrais, identificadores (CNPJ/CNES), DPO e região geográfica.
2. **Liberação de protocolos**: a empresa decide quais protocolos do catálogo estão disponíveis, se são obrigatórios ou opcionais e qual é o padrão institucional de cada escopo de uso.

Rotas e parâmetros estão em `empresa_controllers.md`.

## Perfis

| Perfil | Quem é | O que faz neste domínio |
|---|---|---|
| Anônimo | Quem ainda não tem conta | Cadastra empresa + admin; consulta se CNPJ/CNES já existem |
| Admin | Usuário administrador da empresa | Consulta os dados da empresa e a lista de protocolos |
| Super admin | Admin fundador, criado no cadastro da empresa | Atualiza a empresa; libera, bloqueia e define padrões de protocolos |

O super admin também é a referência do **DPO padrão** da empresa.

## Identificadores: CNPJ e CNES

CNPJ e CNES **não são colunas** da empresa. Cada um é um registro na tabela de identificadores (`EmpresaIdentificador`), com um tipo (`cnpj` ou `cnes`) e um valor. Consequências:

- Os dois são gravados **somente com dígitos**.
- Buscar uma empresa por CNPJ ou CNES é feito por junção com a tabela de identificadores, filtrando pelo tipo.
- No cadastro é obrigatório informar ao menos um dos dois.
- O **CNPJ é fixo após o cadastro** (mudar exige alteração de registro na Receita). O **CNES é editável**, desde que não pertença a outra empresa.
- As rotas de verificação (`existe-cnpj` e `existe-cnes`) aceitam só dígitos e bloqueiam qualquer valor com máscara ou outros caracteres, para evitar um falso "não existe".

## Campos autogerenciáveis x restritos

| Tipo | Campos | Regra |
|---|---|---|
| Autogerenciáveis | `nome_fantasia`, `cnes`, `numero`, `bairro`, `complemento`, `cep`, `dpo_nome`, `dpo_email` | O super admin da empresa altera livremente |
| Fixo após cadastro | `cnpj` | Nunca alterado por atualização |
| Restritos | `status_plano`, `plano` | Ninguém altera pela rota de atualização |

Campos restritos existem porque a empresa não deve conseguir se autoconceder algo (por exemplo, reativar o próprio plano suspenso). O schema de atualização rejeita qualquer campo fora da lista de autogerenciáveis. Quando existir um papel "admin Bion" separado do admin cliente, esses campos deverão migrar para uma rota própria desse papel.

## DPO

O DPO (nome e e-mail) **nunca fica nulo**:

- **No cadastro**: se não informado (ou enviado vazio), usa nome e e-mail do admin que está sendo criado.
- **Na atualização**: se for limpo de propósito (`null` ou texto vazio) ou se já estava vazio (empresas anteriores a esse campo), volta a ser nome e e-mail do super admin da empresa.

## Região geográfica

A região é resolvida pelo **CEP**, no cadastro e quando o CEP muda numa atualização:

- Sem CEP: a empresa fica sem região.
- CEP sem região correspondente: erro de validação no campo `cep`.
- Numa atualização, a região só é recalculada se o CEP enviado for diferente do atual.

## Vínculo empresa-protocolo

Cada empresa tem, para cada protocolo que já tocou, um vínculo (`EmpresaProtocolo`) com:

| Campo | Significado |
|---|---|
| `ativo` | Protocolo liberado (`true`) ou bloqueado (`false`) |
| `politica` | `obrigatorio` ou `opcional` |
| `escopo_default_institucional` | Escopo em que é o padrão da empresa (`triagem`, `consulta`, `ambos`) ou nulo |
| `aprovado_por` / `aprovado_em` | Usuário da sessão e momento (UTC) da última mudança de governança |

Protocolos nunca tocados **não têm vínculo**. Na listagem aparecem como não liberados, sem ficar ausentes.

Cada vínculo tem **um único slot** de padrão institucional, e cada escopo da empresa tem no máximo um protocolo padrão (restrição de unicidade no banco).

## Governança clínica e auditoria

Liberar, bloquear, mudar política e definir padrão são ações de governança clínica:

- Só o **super admin** executa.
- `aprovado_por` e `aprovado_em` são sempre lidos da sessão e do relógio do servidor, **nunca do body**, pois são dados que quem age não deveria conseguir forjar.
- Cada ação é registrada na auditoria como ação sensível (`UPDATE` em sucesso, `NOOP` em falha).

---

# Fluxo: cadastro de empresa com admin

Rota pública `POST /create`. Executado numa única transação.

1. **Validação do schema da empresa.** Normaliza (CNPJ, CNES e CEP ficam só com dígitos; DPO vazio vira nulo) e exige CNPJ ou CNES. Campos desconhecidos são rejeitados.
2. **Preparo do admin.** `is_admin` é forçado para `true`.
3. **DPO padrão.** Se não veio DPO, usa `nome_completo` e `email` do admin.
4. **Unicidade.** CNPJ e CNES informados não podem existir em outra empresa.
5. **Região.** Resolvida pelo CEP.
6. **Transação:**
   1. Monta a empresa e grava CNPJ/CNES como identificadores.
   2. Salva a empresa sem commit (o flush gera o id).
   3. Cria o admin como **super admin** vinculado à empresa, também sem commit.
   4. Commit único.
7. **Falha em qualquer ponto** da transação: rollback completo, nada é gravado.

Resposta: `201` com empresa e admin.

---

# Fluxo: atualização da empresa

Rota `PUT /` (super admin). A empresa vem da sessão.

1. **Carrega a empresa** da sessão (inexistente: não encontrada).
2. **Confere o uuid** da sessão com o da empresa carregada; se não bater, a alteração é recusada.
3. **Valida o schema de atualização** (só campos autogerenciáveis; o endereço aninhado é achatado).
4. **CEP novo?** Se o CEP enviado difere do atual, resolve a região antes de alterar qualquer coisa. CEP sem região interrompe o fluxo sem mudar nada.
5. **CNES.** Se veio e é diferente do atual, confere que não pertence a outra empresa e grava como identificador. Vazio significa "sem mudança" (nunca remove o CNES existente).
6. **Demais campos** são aplicados; se houve região nova, `id_regiao_geografica` é atualizado junto.
7. **DPO.** Se foi limpo de propósito ou já estava vazio, volta ao nome/e-mail do super admin.
8. **Grava com flush** (sem commit próprio). A auditoria registra `UPDATE`, ou `NOOP` se algo falhou.

---

# Fluxo: verificação de identificador

Rotas públicas `GET /existe-cnpj/<cnpj>` e `GET /existe-cnes/<cnes>`.

1. Confere que o valor tem **somente dígitos**; caso contrário, rejeita com erro de validação.
2. Busca a empresa pelo identificador.
3. Responde `{"existe": true | false}`.

---

# Fluxo: liberação de protocolos

## Listagem

`GET /`: o catálogo inteiro é cruzado com os vínculos da empresa. Cada item mostra o protocolo, se está ativo, a política e o escopo em que é padrão.

## Resolução do protocolo

Nas rotas de alteração, o uuid da URL é convertido no protocolo do catálogo **uma única vez**. Uuid inexistente interrompe o fluxo (não encontrado), e a tentativa é auditada como `NOOP` sem id. Se o protocolo existe, o id dele entra na auditoria mesmo quando a regra de negócio recusa a ação.

## Alterar status e política

`PUT /<uuid_protocolo>/status` com `{"ativo": bool, "politica"?: ...}`.

1. Valida o body.
2. Carrega o vínculo da empresa com o protocolo (pode não existir).
3. Calcula a **política final**: a enviada ou, se omitida, a atual (ou `opcional` se não há vínculo).
4. **Regra do obrigatório**: política final `obrigatorio` exige `ativo = true`. Para desativar um obrigatório, enviar `politica = "opcional"` junto.
5. **Se está desativando**, aplica as proteções:
   - O padrão institucional não pode ser desativado.
   - A empresa precisa manter ao menos 2 protocolos ativos: com 2 ou menos ativos, não é possível desativar um protocolo que está ativo.
6. Se não havia vínculo, cria um.
7. Grava `ativo`, a política (se enviada), `aprovado_por` e `aprovado_em`.

| Situação | Resultado |
|---|---|
| Ativar protocolo nunca tocado | Cria o vínculo ativo |
| Desativar obrigatório sem tornar opcional | Recusado |
| Desativar o padrão institucional | Recusado |
| Desativar com 2 ou menos ativos | Recusado |
| Dois admins criando o mesmo vínculo ao mesmo tempo | Um deles recebe conflito ("operação simultânea") e deve tentar de novo |

## Definir padrão institucional

`PUT /<uuid_protocolo>/default` com `{"escopo": "triagem" | "consulta" | "ambos"}`.

1. Valida o body.
2. O protocolo precisa ter vínculo **ativo** com a empresa.
3. O protocolo precisa **servir ao escopo** pedido:

   | Uso do protocolo no catálogo | Pode ser padrão de |
   |---|---|
   | `triagem` | `triagem` |
   | `consulta` | `consulta` |
   | `ambos` | `triagem`, `consulta` e `ambos` |

   Para o escopo `ambos`, só protocolos de uso `ambos` servem.
4. **Slot único**: se o protocolo já é padrão de **outro** escopo, a ação é recusada. É preciso antes definir outro padrão para o escopo de origem.
5. **Troca no mesmo escopo**: se o escopo já tinha outro protocolo padrão, ele perde o slot (`escopo_default_institucional` volta a nulo) e também recebe `aprovado_por` e `aprovado_em`. As duas mudanças ocorrem na mesma transação.
6. O novo padrão recebe o escopo, `aprovado_por` e `aprovado_em`.

---

# Mapa de regras e erros

| Regra | Onde vale | Tipo de erro |
|---|---|---|
| CNPJ ou CNES obrigatório no cadastro | Cadastro | Validação |
| CNPJ/CNES únicos | Cadastro e atualização (CNES) | Conflito |
| CEP precisa ter região | Cadastro e atualização | Validação (campo `cep`) |
| Campos restritos não são aceitos | Atualização | Validação |
| Identificador só com dígitos | Verificação de CNPJ/CNES | Validação |
| Obrigatório exige ativo | Alterar status | Validação |
| Padrão institucional não é desativado | Alterar status | Conflito |
| Mínimo de 2 ativos | Alterar status | Conflito |
| Padrão exige vínculo ativo | Definir padrão | Validação |
| Protocolo precisa servir ao escopo | Definir padrão | Validação |
| Um slot de padrão por vínculo | Definir padrão | Conflito |
| Operação simultânea | Gravação do vínculo | Conflito |