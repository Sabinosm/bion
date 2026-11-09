# Tipo Sanguíneo — Observações de tipo sanguíneo

Documentação do módulo do tipo sanguíneo do paciente, que é **insert-only**. O fluxo completo está em `paciente_fluxo.md`.

---

# Contexto e conceitos

## Visão geral

Cada informação de tipo sanguíneo é uma **observação** datada e imutável. Não há atualizar, remover nem soft delete: **corrigir é registrar uma nova observação**. A **vigente** é a mais recente (data de registro, com o id desempatando).

## Quem lê e quem escreve

- **Leitura:** médico ou enfermeiro da empresa (vigente e histórico).
- **Escrita:** dentro de um **Atendimento em andamento** do próprio profissional (checagem comum de escrita clínica). A observação guarda quem registrou e o atendimento de origem.

## Registrar

| Campo | Regra |
|---|---|
| `tipo_sanguineo` | `A+`, `A-`, `B+`, `B-`, `AB+`, `AB-`, `O+`, `O-` ou `desconhecido` |

A caixa é normalizada antes de validar: `a+`, `A+` e ` A+ ` valem `A+`, e `DESCONHECIDO` vale `desconhecido`.

| Regra | Erro |
|---|---|
| Corpo inválido (erros por campo) | 422 |
| O valor informado **já é o vigente** | 409 |

`desconhecido` é um valor **registrável** (todo paciente tem tipo sanguíneo; "desconhecido" é o estado do que ainda não se sabe). Já "nunca coletado" é a ausência de observação.

## Transação

`commit=False` só faz flush (rota agregada do binário); com `True`, uma falha desfaz tudo.

## Estatísticas

`distribuicao` devolve, por tipo, a quantidade de pacientes da empresa, contando só a observação **vigente** de cada um (maior id por paciente; usar a maior data empatava em inserções no mesmo instante e contava o paciente duas vezes).

---

# Estrutura de arquivos

| Arquivo | Papel |
|---|---|
| `controllers/obs_tipo_sanguineo_controller.py` | Rotas (`bp` de leitura e `bp_escrita`) |
| `services/obs_tipo_sanguineo_service.py` | Regras |
| `repositories/obs_tipo_sanguineo_repository.py` | Acesso a dados e distribuição |
| `schemas/schema_tipo_sanguineo.py` | Schema de entrada |
