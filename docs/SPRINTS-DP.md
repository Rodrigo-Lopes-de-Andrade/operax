<!-- verificar-docs: inexistentes-de-proposito app.benefit_type app.employee_bank_account app.work_post public.fn_dp_panel public.fn_dp_alerts app.work_schedule_day -->
<!-- `app.work_schedule_day` continua aqui porque o Quadro REPORTA que ela não
     existe — e agora a SPEC diz o mesmo, então a contradição entre os dois
     documentos acabou. `app.schedule_rotation_map` SAIU desta lista: ela existe
     (migration 25), e declarar exceção para objeto existente é mentira que o
     verificador não pega, porque ele só suprime e nunca reclama de sobra. -->

# OperaX — sprints da etapa DP

Sequência de implementação de `SPEC-DP.md`. Cinco sprints, ordenados por
dependência real, não por tamanho. Cada um tem um **gate verificável** — se o
gate não fecha, o sprint não terminou, mesmo com o código escrito.

A etapa **não começa** antes da baixa dos 9 ALTA da auditoria e da entrada dos
documentos de decisão ausentes no repositório. E não colide com a etapa de RH:
S1 e S2 são pré-requisito dela também.

---

## S1 — Fundação: postos, catálogo e pacote de remuneração

**Por que primeiro:** sem `benefit_type` e `employee_benefit` a folha base é
incalculável, e é ela que o cliente usa para reconhecer o próprio custo. Sem
`work_post` a rotina de VT não roda. Tudo depende daqui.

- Migrations `dp_work_post`, `dp_benefit_catalog`.
- ⚠️ **`dp_work_post` NÃO cria o elo com a escala.** A premissa de que a escala
  por dia já estava modelada com esse nome era falsa (SPEC §0). O Quadro de
  Postos entra sozinho — `unidade + código` — e o elo posto → escala vira
  migration própria. **Isso não é escopo do S1 e não o bloqueia.**
  ✅ O grão foi lido em 05/09 (SPEC §0-bis): o elo é um `secullum_schedule_id`,
  no idioma de `app.unit_secullum_map` — a migration própria tem forma conhecida,
  e continua fora de S1.
- Semente de `app.benefit_type` com os **9 tipos** e o `composes_base` da tabela
  da SPEC §1d — é a definição do KPI, já revisada pelo owner em 04/09. Transcreva;
  não derive.
- ⛔ **Antes de semear:** a medição da SPEC §1d-bis (existe rubrica de triênio
  separada do salário?). Se não existir, `seniority_bonus` sai da semente — o
  triênio já está no salário e somá-lo conta duas vezes.
- `app.employee_position` ganha `work_post_id` e `level`.
- Backend: `/dp/postos` e `/dp/beneficios/catalogo` + reajuste por vigência.

**Gate:** o teste da folha base passa — salário + ajuda + cargo de confiança +
periculosidade + triênios entram, VR fica fora — sobre fixture sintética. Um
reajuste de tarifa cria vigência nova e **não** altera a anterior. Um aumento de
salário **muda o valor do triênio** na mesma leitura (é taxa, não montante).
`make db-test` verde.

**Linha de reconciliação — condicional, e a condição já foi medida.** Ela só
vale se `seniority_bonus` estiver na semente:

- **Com** triênio na semente: `OperaX − legado = total de triênios`. Diferença
  igual a esse total é aprovação.
- **Sem** triênio na semente (**é o caso hoje** — a medição da §1d-bis mostrou
  que não há rubrica separada): `OperaX − legado = 0`. Qualquer diferença
  reprova.

Manter a versão "com triênio" enquanto ele está fora reprovaria o número certo,
que é exatamente o que esta linha existe para impedir. Ela muda junto com a
semente, sempre — nunca uma sem a outra.

## S2 — Domínio `banking`

**Por que separado:** é a única parte da etapa que mexe na matriz de
sensibilidade. Isolada, ela é revisável em meia hora; misturada, contamina a
revisão do resto.

- `dp_banking_domain` (só o `ADD VALUE`) e, **em arquivo separado**,
  `dp_banking_account` — a limitação do Postgres está na SPEC §1a e não é
  contornável.
- Policies, seed da matriz, `operax/dp/banking.py` com o serializer mascarado.

⛔ **Parada obrigatória antes de aplicar:** policy de RLS nova.

**Gate:** `hr` recebe `permission denied` em `app.employee_bank_account`;
`personnel` lê. Nenhuma resposta de rota contém `account` fora de máscara —
teste que varre o JSON, não revisão de código. Nenhum grant para
`authenticated`.

## S3 — Ciclo mensal: cesta e vale transporte

O sprint que aposenta o legado. Os dois `kind` no mesmo modelo, cesta primeiro
(mais simples: não tem janela nem dias) e VT depois.

- Migration `dp_benefit_cycle`; gatilho de imutabilidade do ciclo gerado.
- Apurador: janela 21→20, faltas do mês civil anterior, `net_days`, total.
- Exports: Excel, PDF e **arquivo de remessa** — este último só para quem tem
  `banking`, montado no backend.

**Gate:** apuração de um mês real de staging confere com o legado **linha a
linha** — não só no total. Divergência de uma pessoa é falha do gate: é onde
mora o erro que tira dinheiro de alguém. Ciclo gerado recusa `update`.

## S4 — Painel de DP e alertas

- `dp_movement_period` (a unidade de atuação passa a ser derivada),
  `dp_leave_extension`, `dp_cadastral_fields`.
- `dp_panel_views`: `public.fn_dp_panel`, `public.fn_dp_alerts`.
- Os dois templates de mensagem sob a regra 11 — `birthday_greeting` e
  `cnh_renewal_request` — com `util.validate_alert_template` cobrindo os dois.

⛔ **Parada obrigatória antes de aplicar:** coluna nova em view pública.

**Gate:** os 9 KPIs batem com o legado sobre a mesma base; os 8 contadores de
alerta usam `app.document_type.expiry_alert_days`, não constante; supervisor
continua sem ver outra unidade; o card de sinistro devolve **contagem**, e o
nome só sai pelo caminho 2 com `compensation`.

## S5 — Laudos e curadoria de rubrica

Os dois menores, juntos porque nenhum bloqueia nada.

- `dp_unit_compliance` + tela em Unidades, com renovação por `replaces_id`.
- `dp_payroll_code_map`, semeada de `app.payroll_entry` — a lista chega pronta
  para a contabilidade conferir, não para levantar.

**Gate:** laudo renovado não deixa duas linhas vigentes para o mesmo (unidade,
tipo); situação é derivada de `valid_until`, não coluna. Código de rubrica não
validado não aparece em indicador financeiro.

---

## Ordem e paralelismo

```
S1 ──┬── S3 ── S4
     │
S2 ──┘        S5  (independente, encaixa em qualquer folga)
```

S1 e S2 podem correr em paralelo por pessoas diferentes: não se tocam. S3 exige
os dois. S5 não exige nenhum.

## O que fecha a etapa

Suíte completa verde; dicionário regenerado; e **duas competências seguidas
fechadas dentro do OperaX** — pedido de cesta e remessa de VT gerados sem abrir
o legado. O segundo mês é o que conta: o primeiro sempre tem alguém ajudando.

## O que continua fora e por quê

Foto do colaborador (não é necessária à operação), delete físico (regra 6
estendida), nome no card de sinistro da home (contagem basta), e os módulos
Comercial, Financeiro e Unidades do legado — não foram vistos. `Unidades` é a
próxima leitura: é onde o cliente mantém o Quadro de Postos hoje, e vale
conferir o que ele guarda lá antes de S1 congelar `app.work_post`.

---

# Quadro de orquestração

⚠️ **Acrescentado em 04/09/2026, com autorização do dono.** O corpo acima é o
plano e **não foi alterado** — nem sprint, nem ordem, nem gate. O que segue é o
andaime que a orquestração exige e que o documento não tinha.

## Status

| Sprint | Status | Slot(s) de migration | Revisores OK | Ciclos |
|---|---|---|---|---|
| S1 — Fundação | **pendente** | `dp_work_post`, `dp_benefit_catalog` | — | 0 |
| S2 — Domínio `banking` | **pendente** | `dp_banking_domain`, `dp_banking_account` | — | 0 |
| S3 — Ciclo mensal | pendente | `dp_benefit_cycle` | — | 0 |
| S4 — Painel e alertas | pendente | `dp_movement_period`, `dp_leave_extension`, `dp_cadastral_fields`, `dp_panel_views` | — | 0 |
| S5 — Laudos e rubricas | pendente | `dp_unit_compliance`, `dp_payroll_code_map` | — | 0 |

Onze slots, um arquivo por slot. ⛔ `dp_banking_domain` e `dp_banking_account`
são **arquivos separados**: o Postgres proíbe usar o valor novo do enum na mesma
transação que o adiciona, e cada migration roda em uma (SPEC §1a).

## ⛔ Por que nada foi despachado

Verificação de 04/09/2026, antes do primeiro despacho, **revista em
05/09/2026** — a coluna Estado é de hoje; as seções abaixo dela são o
registro de como cada uma fechou.

| # | Condição | Estado |
|---|---|---|
| 1 | Os quatro documentos no repositório | ✅ **resolvida em 05/09** — os dois entraram |
| 2a | FORCE em `app` | ⛔ **zero** — ver abaixo |
| 2b | A captura enxerga flags de segurança | ✅ sim: RLS, FORCE, policies, grants e revokes |
| 3 | Medição do §1d-bis | ✅ resolvida: `seniority_bonus` **sai da semente por ora** |
| 4 | Arquivos e critérios preenchidos | ✅ resolvido por este quadro |
| 5 | Sprint pedindo decisão fechada | ✅ **verificada em 05/09** — nenhuma pede |
| 6 | Elenco confere com `/agents` | ✅ resolvido: `guardiao-de-superficie` criado em 04/09 |

### 2a — não existe FORCE em `app`, e a documentação dizia que existia

Medido nos dois lados: `app` tem **54 tabelas em produção e 53 no repositório,
todas com RLS e ZERO com FORCE**. FORCE existe só em `secullum` (20 de 22).

Sem FORCE o **dono da tabela não é filtrado pela RLS**, e o backend conecta como
`postgres`, que é o dono de `app`. O isolamento do Caminho 2 mora inteiro em
`operax/core/tenant.py`, como o `CLAUDE.md` descreve — mas as ~10 tabelas novas
desta etapa nascem na mesma condição, e duas são de domínio sensível.

⛔ **Se FORCE deve passar a valer é decisão de policy de RLS — parada obrigatória
deste projeto, e não se resolve dentro de uma sprint.**

### 2a-bis — ligar FORCE seria um no-op, e isso foi medido em 05/09/2026

⚠️ **A frase acima está certa e o remédio que ela sugere está errado.** É verdade
que sem FORCE o dono não é filtrado. O que faltava medir é que **com** FORCE ele
também não é — porque `postgres` não é só dono, é **`rolbypassrls = true`**, e
BYPASSRLS vence FORCE.

Medido no banco descartável do `db-test`, tabela em `app` com RLS ligada e policy
`using (false)`, duas linhas gravadas:

| # | Dono da tabela | FORCE | Linhas que o dono lê |
|---|---|---|---|
| A | `postgres` (BYPASSRLS) | off | **2** |
| B | `postgres` (BYPASSRLS) | **ON** | **2** |
| C | papel sem BYPASSRLS | **ON** | **0** |
| D | papel sem BYPASSRLS | off | **2** |

**C contra D prova que FORCE não está quebrada** — ela faz exatamente o que a
documentação diz. **A contra B prova que ela não alcança este backend.** Em
produção e no repositório, as 54 tabelas de `app` são de `postgres`, e o
`DATABASE_URL` do backend é `postgresql://postgres@…`.

**Três consequências, e a terceira é a que muda o plano.**

1. **Ligar FORCE em `app` não fecharia exposição nenhuma.** Fecharia a auditoria
   com um verde falso, que é pior que o vermelho honesto: a pergunta sairia da
   lista sem ter sido respondida.
2. **O Caminho 1 nunca dependeu disso.** `authenticated` e `anon` não têm
   BYPASSRLS e não são donos — a RLS os filtra hoje, com ou sem FORCE, e é o que
   os scripts `98` e `99` provam a cada `db-test`.
3. ⛔ **Então a condição 2a, como escrita, NÃO bloqueia S1 e S2.** As ~10 tabelas
   novas nasceriam na condição em que as 54 existentes já vivem — que é a
   condição em que o produto já está no ar. Bloquear a etapa por ela seria exigir
   das tabelas novas uma garantia que nenhuma tabela do produto tem, e que ligar
   FORCE não daria.

📌 **A pergunta real não é FORCE — é o papel de conexão**, e o próprio código já a
tinha nomeado antes desta medição. O docstring de `backend/operax/core/tenant.py`
diz, sobre o lint sintático de `bind_tenant`: *"leia como lint barato na saída,
não como a fronteira de segurança. A fronteira é um papel não-superusuário com
RLS ligada e o tenant setado por transação; isso é decisão de policy e grant,
pendente fora deste módulo."*

**FORCE só passa a significar alguma coisa depois** de o backend conectar como um
papel sem BYPASSRLS. Aí ela deixa de ser opcional. Trocar o papel é trabalho de
verdade — todo `tenant_scope` hoje atravessa por bypass, e passaria a depender de
policies que assumem um JWT que ele não tem — e **não é escopo da etapa DP**.

✅ **Respondida pelo dono em 05/09/2026: a etapa anda**, com o isolamento do
Caminho 2 **declarado** como sendo de código — `core/tenant.py` mais a
revalidação de papel e domínio na rota. É a condição em que as 54 tabelas de hoje
já vivem, e as ~10 novas não a pioram.

📌 **A decisão está registrada em `DECISAO-FRONTEIRA-CAMINHO-2.md`**, com o que
ela assume por escrito (§3), o item que fica no backlog (§4 — a troca do papel de
conexão, com FORCE junto e só junto) e as três coisas que a reverteriam (§5). O
primeiro dos três é o mais próximo: **um segundo tenant real em produção**.

### O §1d-bis não pôde ser medido por dado, e a decisão veio do dono

`app.payroll_entry`, `payroll_event_map` e `payroll_period` têm **0 linhas em
produção**. Não há folha importada, então "existe rubrica de triênio separada do
salário?" não tem resposta empírica.

✅ **Decisão do dono em 04/09: `seniority_bonus` sai da semente por ora.** Os
demais tipos entram. A linha de reconciliação do gate de S1 muda junto: sem o
triênio na semente, `OperaX − legado` deixa de ser "o total de triênios".
**Reescrever essa linha é pré-requisito de despachar S1** — do contrário o gate
reprova por desenho, que é o que ela existia para evitar.

### ✅ `app.work_schedule_day` não existe — e a pergunta que isso abria foi lida

A SPEC §0 citava `app.work_schedule_day` com as colunas
`entry_1 · exit_1 · entry_2 · exit_2` como algo que **já existe**, afirmando que
"falta o elo posto → escala, não a escala". Medido: a tabela **não existe em
produção nem no repositório**.

**Duas coisas fecharam isso, em ordem.**

**1. A SPEC parou de afirmar (04/09).** A revisão que entrou em 05/09 declara a
procedência errada — as verificações rodaram contra um snapshot de 15 migrations,
não contra as 37 — e rebaixa a linha a questão aberta. No mesmo movimento a
`dp_work_post` **perde o `work_schedule_id`**: o Quadro de Postos entra sozinho
(`unidade + código`) e o elo vira migration própria. **É o que destrava S1** — a
sprint deixa de depender da premissa falsa em vez de esperar por ela.

**2. O grão foi lido (05/09).** A SPEC §0-bis registra a medição. Resumo: o
domínio **tem** escala por dia, em três camadas, e nenhuma se chama
`work_schedule_day` — `secullum."HorarioDia"` é a escala por dia da origem
(`Entrada1..5`/`Saida1..5` por `DiaSemana`), `app.schedule_rotation_map` é
curadoria de ciclo para onde a origem cala (12x36), e `app.expected_workday` é a
materialização por `(colaborador, data)` que o `jornada.py` escreve.

⚠️ **O que sobra é forma, não existência.** A escala é propriedade do horário, e
`Funcionario.horario_id` já atribui — então o elo é um `secullum_schedule_id` no
`app.work_post`, no idioma de `app.unit_secullum_map`. **Isso não devolve o elo
para S1:** a `dp_work_post` continua sem ele. Deixa de ser pergunta aberta e
passa a ser trabalho de forma conhecida, numa sprint posterior.

✅ O `CLAUDE.md` §Convenções repetia o erro ("`work_schedule_day`, que já existia
antes deste modelo"). Corrigido em 05/09 para `app.expected_workday`, que é o
objeto que de fato existe desde a migration 05 e sustenta a mesma frase.

### O que ainda impede o despacho, depois de 05/09

**Uma condição, e é a que não se resolve dentro de sprint.**

| # | Condição | Estado |
|---|---|---|
| 1 · 3 · 4 · 5 · 6 | documentos, §1d-bis, arquivos, decisão fechada, elenco | ✅ fechadas |
| 2b | a captura enxerga flags de segurança | ✅ fechada |
| **2a** | **FORCE em `app`** | ⚠️ **reenquadrada em 05/09 — ver §2a-bis.** Ligar FORCE é no-op medido; a pergunta real é o papel de conexão, e ela **não é escopo desta etapa** |

✅ **Nenhuma condição de parada segue aberta.** A 2a foi a última, e a §2a-bis a
fechou em 05/09 — medindo que o remédio que ela pedia era no-op, e levando a
pergunta de fundo para `DECISAO-FRONTEIRA-CAMINHO-2.md`, onde o dono a respondeu.

**S1 e S2 estão despacháveis**, em paralelo, por `/orquestrador-dp`. As paradas
obrigatórias **dentro** das sprints continuam de pé e não foram afrouxadas por
esta decisão: policy de RLS nova em S2, coluna nova em view pública em S4, e a
semente de `app.benefit_type` em S1.

📌 **O `orquestrador-dp` está no repositório desde 05/09**
(`.claude/commands/orquestrador-dp.md`). A parada 1 dele — os quatro documentos —
deixou de disparar; a parada 2 (FORCE) dispara.

## Arquivos por sprint

⚠️ **Procedência:** só `operax/dp/banking.py` é nomeado pela SPEC (§2). Os demais
são **derivados** da convenção do repositório e da seção de rotas e telas —
tratar como proposta a conferir no despacho, não como fato. O agente que precisar
de algo fora da sua lista **reporta em vez de editar**.

**S1** — `supabase/migrations/<ts>_dp_work_post.sql`,
`supabase/migrations/<ts>_dp_benefit_catalog.sql`,
`backend/operax/dp/postos.py`, `backend/operax/dp/beneficios.py`,
`backend/server/routers/dp.py`, `backend/server/models.py`,
`backend/tests/test_dp_beneficios.py`, `frontend/src/app/dashboard/administracao/`

**S2** — `supabase/migrations/<ts>_dp_banking_domain.sql`,
`supabase/migrations/<ts>_dp_banking_account.sql`,
**`backend/operax/dp/banking.py`** (nomeado pela SPEC §2),
`backend/server/routers/dp.py`, `backend/tests/test_dp_banking.py`,
`scripts/98_teste_isolamento_tenant.sql`

**S3** — `supabase/migrations/<ts>_dp_benefit_cycle.sql`,
`backend/operax/dp/ciclo.py`, `backend/operax/dp/export.py`,
`backend/server/routers/dp.py`, `backend/tests/test_dp_ciclo.py`,
`frontend/src/app/dashboard/dp/`

**S4** — as quatro migrations do slot, `backend/operax/dp/painel.py`,
`backend/server/routers/dp.py`, `frontend/src/app/dashboard/dp/`,
`scripts/99_verificacao_rls.sql`

**S5** — `supabase/migrations/<ts>_dp_unit_compliance.sql`,
`supabase/migrations/<ts>_dp_payroll_code_map.sql`,
`backend/operax/dp/laudos.py`, `backend/operax/dp/rubricas.py`,
`frontend/src/app/dashboard/administracao/`

## Elenco

| Papel | Agente |
|---|---|
| Banco | `fastapi-developer` (cobre backend **e** banco) |
| Backend | `fastapi-developer` |
| Frontend | `nextjs-developer` |
| Revisor de código | `code-reviewer` |
| **Guardião de superfície** | **`guardiao-de-superficie`** — criado em 04/09 |
| **Orquestrador** | **`/orquestrador-dp`** — versionado em 05/09 |

## A pergunta do falso verde, aplicada aos gates existentes

Feita antes de aceitar cada conjunto. Resultado: **os gates do plano têm o
positivo** e não precisam de acréscimo.

- **S2** — *"`hr` recebe `permission denied`"* é só-negativo e ficaria verde num
  banco onde ninguém lê nada. ✅ O plano já traz *"`personnel` lê"* ao lado.
- **S4** — *"supervisor continua sem ver outra unidade"* idem. ✅ O guardião
  carrega o positivo *"e vê a dele"*.
- **S1, S3, S5** — os gates são de igualdade contra o legado (folha base, linha a
  linha, vigência única), que são positivos por construção.
