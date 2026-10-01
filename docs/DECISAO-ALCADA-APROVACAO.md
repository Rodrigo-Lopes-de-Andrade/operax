
# OperaX — decisão: alçada de aprovação de justificativas

**Origem:** pedido do cliente, transmitido junto com o documento de contexto da
equipe do Secullum (tolerâncias e feriados), em 28/09/2026.

> *"Precisamos desenvolver alçadas de aprovação para justificativas: o supervisor
> identifica, registra e envia ao RH da administração os desvios e justificativas,
> e abona ou reprova. O RH, em um período específico do mês, confirma com o
> supervisor e registra no sistema que serve de base para a folha."*

---

## 1. Decisões do owner (28/09/2026)

| # | Decisão |
|---|---|
| 1 | **O Secullum continua sendo o registro e o PTRP.** O RH aprova no OperaX e **lança no Secullum**. O OperaX é fluxo, evidência e trilha. |
| 2 | **O supervisor pode justificar os próprios desvios. Quem aprova é sempre o RH.** |
| 3 | **A competência da folha é a mesma 21→20 do VT.** |
| 4 | **Período 21→20 fechado nos dois lados**, com **regra de atraso separada**. |
| 5 | **O RH digita no Secullum.** Sem escrita por API e sem arquivo de importação. |

⚠️ **A decisão 4 revisa uma resposta anterior da mesma conversa.** A primeira
formulação foi *"o desvio do dia 20 pertence à competência seguinte"*, que,
aplicada para trás, transformava a janela real em 20→19 e fazia o nome "21 a 20"
mentir. Vale a formulação da tabela: **o desvio do dia 20 pertence à competência
que fecha no dia 20**, e o que rola para a seguinte é o que **chega** depois do
fechamento.

### 1.1 Por que a decisão 2 é mais forte do que parece

Ela não diz "você não mexe no seu". Diz **ninguém aprova o próprio, porque
aprovar é sempre de outro papel**. Uma regra, sem exceção a manter, e sem a
trava frágil de comparar autor com titular.

⛔ **Consequência em aberto:** se aprovar é sempre do RH, **quem aprova o desvio
de alguém do RH?** Sem resposta, o primeiro atraso de um analista de RH trava
numa fila sem aprovador. Ver §7.

---

## 2. O que já existe, e muda o desenho

Levantado contra `DICIONARIO-DE-DADOS.md` (gerado do schema, 28/09/2026). Este
documento **não** assume o repositório público do GitHub, que está atrasado em
relação a este dicionário.

### 2.1 `app.justification` existe, e a lacuna está escrita na própria coluna

```
deviation_event_id · employee_id · reference_date · text
source in ('secullum','operax','whatsapp')
author_user_id · author_name
status in ('accepted','rejected')   default 'accepted'
```

O comentário da coluna `status` descreve o problema do cliente antes de ele
pedir:

> *"Default accepted de propósito: até esta migration uma linha aqui ERA a
> resposta final, e nenhuma justificativa já escrita pode virar pendente
> retroativamente. **Não existe tela que rejeite** — enquanto não existir,
> 'aceita' e 'escrita' são a mesma coisa."*

Três consequências de forma:

1. **Falta `pending`**, e a migration que o criar **não pode** tornar pendente o
   que já foi escrito. A restrição está avisada na própria coluna.
2. **Não existe policy de UPDATE** — só `justification_read` (SELECT) e
   `justification_write` (INSERT). Ninguém altera justificativa pelo painel.
   **Isso é acerto, não lacuna**, e decide a §3: a aprovação do RH é **fato
   novo**, nunca edição do fato anterior.
3. **`source` tem três valores, e dois deles mudam o fluxo.** Justificativa com
   `source='secullum'` **já foi decidida no registro oficial** e não pode entrar
   na fila do OperaX: seria reaprovar o que a fonte da verdade resolveu.
   E `source='whatsapp'` chega com `author_user_id` nulo e `author_name`
   preenchido, então o fluxo aceita autor que não é usuário do painel.

### 2.2 `app.payroll_period` já é a competência, com ciclo de vida

```
(tenant_id, year, month)   month vai até 13 (décimo terceiro)
status in ('aberta','importada','conferida','fechada')
closed_at
```

**Não criar tabela de competência.** Ela existe, e o passo do cliente — *"o RH,
em um período específico do mês, confirma"* — já tem nome nela: **`conferida`**.

⚠️ Ela guarda `year`/`month`, **não** `period_start`/`period_end`. A janela
21→20 é **derivada**, nunca armazenada:

```sql
create or replace function util.competencia_janela(p_year int, p_month int)
returns daterange ...   -- [dia 21 do mês anterior, dia 20 do mês] fechado
```

Uma definição só, num lugar só. Guardar as datas criaria duas linhas capazes de
discordar sobre o mesmo mês, que é a classe de erro que este produto recusa.

### 2.3 `app.report_cycle` NÃO é competência

`open/sent/failed/cancelled`, com `channel`, `sent_at`, e **por unidade**. É
ciclo de **envio de relatório**.

⛔ **Não reaproveitar** só porque tem `period_start`/`period_end`. Se a
competência morar nele, cancelar um envio passa a mexer em folha, e o RH fecha
24 vezes em vez de uma.

---

## 3. O achado que decide a arquitetura — e ele está provado

**A justificativa não sobrevive a um reprocessamento do motor.**

O insert do motor (`backend/operax/motor/regras.py:271`) é
`on conflict (employee_id, reference_date, type, mode) where status = 'active'`.
Os dois índices alvo continuam, no dicionário de hoje, restritos a
`status = 'active'`. Quando o supervisor justifica, a linha **sai do índice**, o
conflito deixa de existir, e o insert seguinte **cria linha nova**.

Reproduzido em PostgreSQL 16.13 sobre o grão real das migrations 05 e 18:

| Passo | Resultado |
|---|---|
| Motor roda | 1 linha `active/40` |
| Motor roda de novo | 1 linha `active/45` — reescreve, não duplica ✓ |
| Supervisor justifica | 1 linha `justified/45` |
| **Motor roda depois da justificativa** | **2 linhas: `justified/45` + `active/45`** |

O desvio volta para a fila como se ninguém tivesse olhado, e o sintoma só
aparece no segundo mês.

**A intuição certa já está no código.** O `do update` carrega
`where report_cycle_id is null` — alguém já pensou *"não reescreve o que já foi
reportado"*. Só não estendeu para *"não recria o que já foi julgado"*. O conserto
é a extensão de um cuidado existente.

### 3.1 O conserto, e por que não é no índice

Tentação: alargar o índice para `where status in ('active','justified')`. **Não.**
A migration 18 raciocinou o predicado desses índices em 28 linhas de cabeçalho e
escreveu a regra: *"remover uma garantia para acrescentar uma mais ampla é como
uma garantia se perde num diff"*.

O conserto vai na **origem do insert**: o `select` que alimenta o motor não emite
evento para `(employee, data, tipo)` que já tenha justificativa `accepted`.
Aditivo, testável, e não toca o grão.

⛔ **Teste obrigatório:** as quatro linhas da tabela acima viram
`scripts/teste_justificativa_sobrevive.sql`. A quarta é a que nenhuma revisão de
código pega.

---

## 4. A forma

### 4.1 `alcada_justification_pending` — o estado que falta

```sql
alter table app.justification
  drop constraint justification_status_check,
  add  constraint justification_status_check
       check (status in ('pending','accepted','rejected'));

alter table app.justification alter column status set default 'pending';
```

⚠️ **Alterar o default NÃO toca linha existente.** É exatamente o que o
comentário da coluna exige, e é por isso que a migration não pode ter `update`
retroativo.

E a regra da §2.1 item 3 vira estrutura em vez de parágrafo:

```sql
alter table app.justification
  add constraint justification_espelho_nao_pende
      check (source <> 'secullum' or status = 'accepted');
```

Justificativa espelhada da origem **não consegue** nascer pendente nem ser
reprovada no OperaX. O banco recusa.

### 4.2 `alcada_justification_review` — a aprovação como fato novo

```sql
create table if not exists app.justification_review (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references app.tenant(id) on delete cascade,
  justification_id  uuid not null references app.justification(id) on delete cascade,
  payroll_period_id uuid not null references app.payroll_period(id),
  decision          text not null check (decision in ('approved','rejected')),
  reason            text,
  reviewed_by       uuid not null references auth.users(id),
  reviewed_at       timestamptz not null default now(),
  posted_to_source_at timestamptz,
  posted_by         uuid references auth.users(id)
);

create unique index if not exists justification_review_uk
  on app.justification_review (justification_id);
```

Quatro escolhas, e cada uma tem motivo:

- **`unique (justification_id)`** — uma revisão por justificativa. Reprovada, o
  supervisor escreve justificativa **nova**, que ganha a própria revisão. A
  trilha fica completa sem nenhum `update`.
- **`payroll_period_id` aponta a competência em que o RH *processou*, não a do
  fato.** É aqui que a decisão 4 vira código: o desvio pertence para sempre à
  competência de `reference_date`; a **revisão** pertence à competência em que
  foi feita. Justificativa que chega depois do fechamento é revisada na
  competência aberta, e nada reabre.
- **`reviewed_by` é `not null`** — revisão sem autor não é alçada.
- **`posted_to_source_at` / `posted_by`** — a decisão 5 diz que o RH digita no
  Secullum. Sem essas duas colunas, ninguém consegue responder *"o que já foi
  lançado e o que não foi"*, e a digitação manual vira buraco silencioso. Esta
  é a coluna que torna a decisão 5 auditável.

⛔ **Parada obrigatória:** tabela nova em `app` com policy de RLS.

**Policies:**

```sql
-- leitura: quem enxerga o colaborador enxerga a revisão
create policy review_read on app.justification_review
  for select to authenticated
  using (exists (select 1 from app.justification j
                  where j.id = justification_id
                    and util.can_see_employee(j.employee_id)));

-- escrita: NENHUMA policy para authenticated.
-- A revisão entra só pelo RPC da §4.3, que checa o papel.
```

### 4.3 `alcada_review_fn` — o RPC que faz a alçada existir

`app.revoke_deviation` está concedido a `authenticated` **sem checagem de
papel**: hoje qualquer usuário que enxerga o desvio pode justificá-lo. É esse
grant que a alçada substitui.

```sql
create or replace function public.fn_revisar_justificativa(
  p_justification_id uuid, p_decision text, p_reason text)
returns uuid
language plpgsql security definer set search_path = ''
```

Validações, na ordem, cada uma com código próprio:

1. `not_hr` — o chamador não tem papel `hr` nem `owner` no tenant. **A função é
   `security definer` e não herda RLS: ela checa o papel ela mesma.** Vem antes
   de qualquer lock: quem não alcança a linha não espera por ela.
2. `justification_not_found` — inexistente, ou de outro tenant. As recusas
   seguintes dizem algo da linha e só vêm depois desta.
3. `own_justification` — o chamador é o autor (`author_user_id`). Autor nulo
   não bloqueia. Vale para o `owner` também. *(Decisão do dono, 29/09.)*
4. `owner_only` — colaborador com `approval_owner_only` e chamador não `owner`.
5. `already_reviewed` — já tem revisão.
6. `source_is_mirror` — `source='secullum'`. Não se reaprova a origem.
7. `not_pending` — a justificativa não está `pending`. Depois do 6 porque
   espelho nunca é pendente. *(Decisão do dono, 29/09.)*
8. `no_open_period` — não há `payroll_period` **não fechada** (meses 1–12) para
   receber a revisão; vai para a mais antiga. Nada no sistema grava `aberta` —
   o import grava `importada`. *(Decisão do dono, 29/09.)*
9. `rejection_needs_reason` — reprovar sem motivo é reprovar sem alçada.

O texto que vale é o cabeçalho de
`supabase/migrations/20260929114738_alcada_justification_review.sql`.

Aprovada, a função escreve a revisão **e** move `deviation_event.status` para
`justified` — o desfecho, escrito uma vez, no fim. Reprovada, o desvio
**continua `active`** e volta para a fila do supervisor.

⚠️ `trg_lock_down_new_function` não cobre `public`: o `grant execute` precisa
estar **escrito** na migration.

### 4.4 `alcada_fila` — a leitura

`public.fn_fila_aprovacao(p_year, p_month, p_unit_id, p_employee_id)` devolve a
fila da competência, com os filtros que o cliente pediu: **competência**,
**funcionário** e **data**. A janela sai de `util.competencia_janela`, nunca de
constante no código.

⚠️ Filtro por funcionário é dado individual: **Caminho 2**, nunca a chave
anônima. E o filtro não pode virar contorno de escopo — supervisor continua sem
alcançar outra unidade.

---

## 5. O que precisa vir ANTES da alçada

Isto não é preferência de sequência. São dois envenenadores medidos da fila que
a alçada vai criar.

### 5.1 Os seis supervisores geram ~130 faltas falsas por mês

`DECISAO-VERDADE-DE-REFERENCIA-G4.md` mediu: os seis supervisores têm escala
Seg–Sex 08:00–18:00, **não batem ponto**, e não têm justificativa registrada.
Eles emitem `no_punches` todo dia útil.

Junto com a decisão 2 (quem aprova é o RH), a consequência é direta: **a primeira
coisa que a alçada faz é pôr o RH para aprovar cerca de 130 faltas fictícias dos
próprios supervisores**, antes de chegar a um desvio real.

### 5.2 Feriado é tratado como folga, e não existe calendário

Varredura no dicionário inteiro: **nenhuma tabela de feriado**. Confirma o
levantamento da equipe do Secullum — `HorarioFaixasExtras.DiaSemana = 3` é regra
de **categoria**, não marcação por data.

Logo, quem trabalha em feriado gera `punch_on_day_off`. Numa operação de
estacionamento, feriado é dia de movimento: a fila enche de dezenas a centenas de
itens, todos pelo mesmo não-motivo.

**E o dano de segunda ordem é pior que o volume:** fila que enche ensina o
aprovador a aprovar em lote sem ler. O controle morre por ruído, não por má-fé.

`app.holiday` precisa de **abrangência** (nacional / estadual / municipal) e
vínculo com unidade: com unidades em cidades diferentes, **feriado municipal
varia por unidade**.

### 5.3 A ordem

```
P0  supervisores que não batem ponto  ─┐
P0  calendário de feriados            ─┼─► P1 alçada
P0  motor não recria o que foi julgado ┘
```

Os três P0 são pré-requisito. O terceiro é a §3.

---

## 6. O risco de adoção, medido

`DECISAO-VERDADE-DE-REFERENCIA-G4.md`, sobre 2.121 linhas de `secullum."Batida"`:

| Campo de adjudicação da origem | Preenchido |
|---|---|
| `"Ajuste"` | 1 |
| `"Abono2"` / `"Abono3"` / `"Abono4"` | **0** |
| `"Observacoes"` | 0 |

E dos **326 dias-colaborador** com **820 indícios ativos em sombra**, apenas
**6** têm rótulo.

**O cliente praticamente não justifica dia no Secullum hoje.** A decisão 5 pede
que o RH passe a usar um fluxo que a empresa nunca usou. Não invalida a decisão,
que continua certa pelo argumento do PTRP, mas é o maior risco do projeto e
**não é de engenharia**. Precisa de combinado explícito com o RH sobre quem
digita, quando, e o que acontece quando não digitam — que é o que
`posted_to_source_at` (§4.2) existe para tornar visível.

---

## 7. Perguntas abertas — do cliente, não da implementação

1. **Quem aprova o desvio de alguém do RH?** Owner, outro membro do RH, ou o
   desvio de quem tem papel `hr` não entra na fila. Sem resposta, trava.
2. **A competência 21→20 move também a janela das faltas?** O
   `ANEXO-COBERTURA-LEGADO-FASTPARK` §4.3 registra da tela do legado: a janela do
   VT é 21→20, mas *"faltas injustificadas: **mês civil anterior** ao início do
   período"*. As duas regras convivem hoje, e o anexo instrui *"copiar literal,
   não reinventar"*. A decisão 3 diz que a folha usa 21→20; falta dizer se as
   faltas continuam vindo do mês civil.
3. **Motivo do abono: catálogo ou texto livre?** `app.justification.text` é
   livre hoje. Para algo que alimenta folha e pode virar prova, catálogo vale
   mais: é auditável, contável, e vira indicador. Se 30% dos abonos forem "erro
   de marcação", o problema é o relógio ou o treinamento, não as pessoas. Texto
   livre nunca conta isso. **Sugiro catálogo com campo livre complementar.**
4. **Qual supervisor aprova quando a pessoa mudou de unidade?**
   `deviation_event.unit_id` é desnormalizado no momento do fato, de propósito.
   O desvio pertence à unidade antiga; quem consegue falar com a pessoa é o
   supervisor atual.

---

## 8. Sprints

**A0 — Reconferência.** Este documento foi escrito contra o `DICIONARIO-DE-DADOS`
de 28/09 e **não** contra o repositório público, que está atrasado. Conferir que
`app.justification`, `app.payroll_period` e os dois índices únicos de
`deviation_event` continuam como a §2 descreve.

**P0.1 — O motor não recria o que foi julgado.**
*Gate:* as quatro linhas da §3 como teste, e a quarta precisa falhar antes do
conserto e passar depois. Teste que não fica vermelho primeiro não provou nada.

**P0.2 — Quem não bate ponto não gera falta.**
*Gate:* rodar o motor sobre a semana medida e os seis supervisores saírem com
zero `no_punches`, sem que nenhum outro tipo mude de contagem.

**P0.3 — `app.holiday`, com abrangência e unidade.**
*Gate:* feriado municipal de uma cidade não suprime desvio em unidade de outra.
⛔ Parada obrigatória: tabela nova em `app` com policy.

**P1.1 — `pending` + a trava do espelho.**
*Gate:* nenhuma justificativa existente vira pendente; `source='secullum'` com
`status='pending'` é **recusado pelo banco**.

**P1.2 — Revisão e RPC.**
*Gate:* supervisor recebe `not_hr`; segunda revisão recebe `already_reviewed`;
reprovar devolve o desvio para `active`; aprovar move para `justified` e grava a
revisão **na mesma transação**; `grant execute` escrito na migration.

**P1.3 — Fila e filtros.**
*Gate:* competência, funcionário e data filtram; supervisor não alcança outra
unidade por nenhum dos três; a janela vem de `util.competencia_janela`.

**P1.4 — Lançamento no Secullum.**
*Gate:* a tela mostra o que falta lançar, e `posted_to_source_at` distingue
"aprovado" de "aprovado e lançado". Sem isso a decisão 5 é invisível.

---

## 9. O que não entra

- **Escrita no Secullum por API** (decisão 5). O POST existe no manual, a
  resposta é indocumentada, e chamar é POST sobre o registro oficial do cliente.
- **Reabrir competência fechada.** A regra de atraso da §4.2 resolve sem reabrir.
- **Alterar justificativa.** Não há policy de UPDATE, e é acerto: correção é
  justificativa nova.
- **Aprovação por WhatsApp.** `source='whatsapp'` entra como justificativa; a
  **revisão** é sempre no painel, com usuário autenticado e papel checado.
