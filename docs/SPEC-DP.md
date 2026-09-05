<!-- verificar-docs: inexistentes-de-proposito app.employee_bank_account app.work_post app.benefit_type app.benefit_plan app.transport_fare app.employee_benefit app.benefit_cycle app.benefit_entitlement app.unit_compliance_report app.payroll_code_map app.employee.hr_code public.fn_dp_panel public.fn_dp_alerts public.vw_unit_compliance app.work_schedule_day -->
<!-- `app.work_schedule_day` entra na lista porque a §0 e a §0-bis a CITAM para
     dizer que ela NÃO existe — foi o nome errado que esta SPEC afirmou como
     existente até 05/09/2026. As demais são entidades que a etapa vai criar. -->

# OperaX — SPEC técnica da etapa DP

O **como** desta etapa. O quê e o porquê estão em `PRD-DP.md`; o levantamento
que a originou, em `ANEXO-COBERTURA-LEGADO-FASTPARK.md`. Complementa
`SPEC-TECNICA.md` e `SPEC-RH.md`.

⚠️ **Procedência das afirmações desta SPEC — leia antes de confiar na §0.**

As verificações que originaram este documento rodaram contra um snapshot de
**15 migrations**, não contra o repositório em andamento (37) nem contra
produção. As duas bases divergem: `app.work_schedule_day` existe no snapshot e
**não** existe no repositório em andamento, onde há `schedule_rotation_map`.

Consequência: **toda linha da §0 que diz "já existe" precisa ser reconferida
contra o repositório em andamento antes de virar código.** Não é uma linha
errada — é uma base de verificação errada, e o que ela produziu de certo foi por
coincidência de nome, não por método.

O que sobreviveu a essa reconferência fica marcado ✅ nesta seção; o que não foi
reconferido fica ⏳. Nada ⏳ entra em migration.

**Em 05/09/2026 o único ⏳ desta SPEC foi lido e virou ✅** — a §0-bis registra a
medição. Nenhuma linha da §0 segue pendente de reconferência.

**Referência de migration é por nome de arquivo, nunca por ordinal** (A11 da
auditoria). Os nomes abaixo são sufixos para `supabase migration new`.

---

## 0. O que já existe e não se reconstrói

| Objeto | O que já resolve |
|---|---|
| `app.sensitive_domain` | enum `pii · compensation · health · disciplinary` — o quarto eixo é um valor a mais |
| `util.can_see_domain` | leitura de `app.tenant_member` + `app.domain_permission`; nenhuma função nova |
| `app.payroll_entry` | `code · description · nature · reference · amount` — a rubrica do legado, coluna a coluna |
| `app.document` | `replaces_id` — o padrão de renovação versionada que os laudos reusam |
| `app.unit` (`address`) + `app.company` (`cnpj`) | o pedido de cesta agrupado por unidade |
| ✅ **escala por dia** (três camadas) | **Respondido por leitura em 05/09/2026 — ver nota abaixo da tabela.** O domínio **tem** escala por dia; ela só nunca se chamou `app.work_schedule_day` |
| `app.document_type` | `requires_expiry · expiry_alert_days · domain` — a janela do alerta é configuração |
| `app.file_import` | `layout_version · rows_ok · rows_error · report` — a esteira de import por tipo |

### 0-bis. A escala por dia — o ⏳ desta seção, lido em 05/09/2026

A linha original não inventou o conceito: **errou o nome e a camada.** O que
existe são três objetos, e confundi-los é o que produziu a afirmação falsa.

| Camada | Objeto | Grão | O que é |
|---|---|---|---|
| Origem | `secullum."HorarioDia"` | `(horario_id, "DiaSemana")`, `DiaSemana` 0–6 | **É a escala por dia**, com `Entrada1..5`/`Saida1..5` — a forma `entry_1 · exit_1 · entry_2 · exit_2` que a linha atribuía ao domínio. Registro oficial |
| Curadoria | `app.schedule_rotation_map` | `(tenant_id, secullum_schedule_id)` | **NÃO é escala por dia.** É âncora + comprimento de ciclo, um par entrada/saída. Existe só para o **silêncio** da origem — 12x36 e afins, que não fecham em sete dias. Linha sem `validated_at` o motor não lê |
| Domínio | `app.expected_workday` | `(employee_id, reference_date)` | A escala por dia **materializada por pessoa**, com `day_type`, `expected_entry`, `expected_exit`, `workload_minutes` e `confidence`. É o produto das duas de cima, escrito por `jornada.py` |

**O que isso responde, e o que não responde.**

✅ **Responde:** o produto tem escala por dia. Ela é lida da origem, corrigida
pela curadoria onde a origem cala, e materializada por pessoa e por data.

⚠️ **A consequência para o elo posto → escala é de forma, não de existência.** A
escala é propriedade do **horário**, não da pessoa e não do posto — o comentário
da migration 25 diz isso com todas as letras, e `Funcionario.horario_id` já faz a
atribuição. Então o elo, quando existir, é um `secullum_schedule_id` no
`app.work_post` — o mesmo idioma de `app.unit_secullum_map` e
`app.schedule_rotation_map` —, **nunca** uma FK para tabela de escala por dia,
que no domínio é derivada e não cadastro.

⛔ **Isto NÃO devolve o elo para dentro de S1.** A `dp_work_post` continua sem
ele, como a §1c decide. O que muda é que a migration própria do elo deixa de ser
pergunta aberta e passa a ser trabalho de forma conhecida.

## 1. Banco

Onze migrations, todas idempotentes, cada uma terminando em bloco `do $$` que
falha alto. Ordem obrigatória: 1 e 2 antes de tudo; 3 antes de 5; 4 antes de 5.

### 1a. `dp_banking_domain` — só o valor do enum

```sql
alter type app.sensitive_domain add value if not exists 'banking';
```

**Sozinha no arquivo, e é de propósito.** O Postgres aceita `ADD VALUE` dentro
de transação, mas **proíbe usar o valor novo na mesma transação** — e cada
migration do Supabase roda em uma. Semear `app.domain_permission` com `banking`
aqui falha com `unsafe use of new value`. Quem juntar as duas descobre isso no
deploy, não no teste.

### 1b. `dp_banking_account` — tabela, policies e permissão

Tabela apartada, e não colunas em `app.employee_pii`: o domínio de conta é
`banking`, não `pii`, e misturar os dois faria a policy de PII governar dado que
não é dela.

```sql
create table if not exists app.employee_bank_account (
  employee_id uuid primary key references app.employee(id) on delete cascade,
  tenant_id   uuid not null references app.tenant(id) on delete cascade,
  bank_code   text not null,
  branch      text not null,
  account     text not null,
  account_type text not null default 'checking'
    check (account_type in ('checking','savings','salary','payment')),
  holder_document text,          -- quando a conta não é do próprio colaborador
  updated_at  timestamptz not null default now()
);
```

RLS: leitura e escrita só com `util.can_see_domain(tenant_id, 'banking')` **e**
`util.can_see_employee(employee_id)` — os dois eixos, como toda tabela sensível
do projeto. Sem grant para `authenticated`: esta tabela nunca é lida pelo
PostgREST, só pelo FastAPI (caminho 2).

Seed da matriz, na mesma migration:

```sql
insert into app.domain_permission (tenant_id, role, domain, allowed)
select t.id, r.role, 'banking'::app.sensitive_domain,
       r.role in ('owner','personnel','accounting')
from app.tenant t
cross join (select unnest(enum_range(null::app.user_role)) as role) r
on conflict (tenant_id, role, domain) do nothing;
```

`hr` fica de fora deliberadamente — mesma lógica da nota que já existe em
`02_tenancy_rls`: quem cuida de saúde não precisa de conta, e o inverso vale.

⛔ **Parada obrigatória.** Policy de RLS nova. Não aplicar sem confirmação
explícita, mesmo estando escrito aqui.

### 1c. `dp_work_post` — Quadro de Postos

```sql
create table if not exists app.work_post (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenant(id) on delete cascade,
  unit_id   uuid not null references app.unit(id),
  code      text not null,                    -- "7703" no legado
  name      text,
  active    boolean not null default true,
  created_at timestamptz not null default now(),
  unique (tenant_id, unit_id, code)
);
```

A tela de VT do legado declara a regra: *"a escala é obtida do Quadro de Postos
(código do posto + unidade)"*. A unicidade acima é essa frase.

**O elo com a escala saiu desta migration, de propósito.** A versão anterior
tinha `work_schedule_id`, apoiada na premissa — falsa — de que a escala por dia
já estava modelada. Sem saber o que `app.schedule_rotation_map` guarda, uma FK
aqui seria chute travando S1 inteiro.

`app.work_post` se sustenta sozinho: o Quadro de Postos é `unidade + código`, e
a rotina de VT precisa dele para exibir o rótulo da escala. **O elo posto →
escala vira migration própria**, numa sprint posterior, depois que alguém ler o
grão de `schedule_rotation_map`. Desacoplar destrava S1 sem fingir que a
pergunta foi respondida.

`app.employee_position` ganha `work_post_id uuid references app.work_post(id)` e
`level text` (o "Nível: OPERADOR" da ficha) — aditivo, anulável.

### 1d. `dp_benefit_catalog` — catálogo com vigência

Quatro tabelas. **`benefit_type.composes_base` é a regra 8 do PRD virando
coluna**: a fórmula da folha base deixa de ser constante no backend.

```sql
create table if not exists app.benefit_type (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenant(id) on delete cascade,
  code text not null,              -- cost_allowance, meal_voucher, trust_position…
  name text not null,              -- rótulo pt-BR da UI
  composes_base boolean not null,  -- entra na "folha salarial base"?
  domain app.sensitive_domain not null default 'compensation',
  active boolean not null default true,
  unique (tenant_id, code)
);
```

Semente que reproduz o legado, e que é a definição do KPI:

| `code` | `composes_base` | origem na tela |
|---|---|---|
| `cost_allowance` | **true** | "Ajuda de custo — compõe a folha base" |
| `trust_position` | **true** | card "Cargo confiança + periculosidade — compõe" |
| `hazard_pay` | **true** | mesmo card — **separado de propósito** (owner, 04/09) |
| `seniority_bonus` | **true** | triênios — **decisão do owner (04/09); não está na fórmula do legado**, ver §1d-bis |
| `meal_voucher` | **false** | "VR — fora da folha base de remuneração" |
| `food_basket` | false | cesta |
| `transport_voucher` | false | VT |
| `health_plan` | false | plano de saúde |
| `dental_plan` | false | plano odontológico |

Nove tipos. `trust_position` e `hazard_pay` ficam **separados** por decisão do owner,
embora o legado os mostre num card só: a soma é idêntica e a distinção se
perde para sempre se nascer fundida. Consequência para o gate do S1: comparar
`trust_position + hazard_pay` contra o card único deles — diferença ali é de
forma, não de valor.

### 1d-bis. Triênios — a exceção que o gate precisa conhecer

O owner decidiu (04/09/2026) que triênios **compõem** a folha base. Duas
consequências que não podem ser descobertas durante o gate:

**1. Isso faz o número divergir do legado, de propósito.** A fórmula na tela do
cliente é `salário + ajuda + cargo conf. + periculosidade` — triênios não
aparecem. Então o gate do S1 ("bate na vírgula") passa a ter **uma linha de
reconciliação declarada**: `OperaX − legado = total de triênios`. Divergência
igual a esse total é aprovação; qualquer outro valor é falha.

**⛔ Antes de semear, uma medição decide se a decisão é aplicável:**

- Algum colaborador tem triênios > 0? (na ficha inspecionada o valor era `0`)
- Existe rubrica de triênio/adicional por tempo de serviço em
  `app.payroll_entry`, separada do salário?

Se a rubrica **existe separada**, a decisão vale como está. Se **não existe**, o
triênio provavelmente já está embutido no salário base do legado — e somá-lo de
novo **conta duas vezes**. Nesse caso a decisão cai por fato novo, não por
mudança de opinião, e este parágrafo é o registro do porquê.

**2. Triênio é taxa, não montante.** Na ficha é uma **contagem** (`TRIÊNIOS: 0`),
não um valor: o montante deriva de contagem × percentual × salário. Guardado
como `amount` fixo, ele congela — o colaborador recebe aumento, o triênio
deveria acompanhar, e o valor fica velho em silêncio. Num tipo que compõe a
base, isso corrompe o KPI sem nenhum sintoma.

Por isso `app.benefit_type` ganha `calculation` (`fixed_amount` | `salary_rate`)
e `app.employee_benefit` ganha `rate numeric(6,4)` e `quantity smallint`,
ambos anuláveis. Para `seniority_bonus`: `quantity` = número de triênios,
`rate` = percentual por triênio, `amount` nulo — o valor é derivado na leitura,
sempre sobre o salário vigente. Os outros oito seguem `fixed_amount` e ignoram
as duas colunas novas.

`app.benefit_plan` (operadora e valor por plano) e `app.transport_fare` (tipo de
tarifa: unitário e ida-e-volta) seguem o padrão de vigência que
`app.employee_compensation` já usa — `effective_from` / `effective_to`, nunca
`update` no valor. Um reajuste é uma linha nova; a tela de "Reajuste" do legado
é exatamente isso.

`app.employee_benefit` liga colaborador ↔ tipo ↔ vigência:

```sql
create table if not exists app.employee_benefit (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenant(id) on delete cascade,
  employee_id uuid not null references app.employee(id) on delete cascade,
  benefit_type_id uuid not null references app.benefit_type(id),
  effective_from date not null,
  effective_to   date,
  amount numeric(12,2),
  benefit_plan_id  uuid references app.benefit_plan(id),
  transport_fare_id uuid references app.transport_fare(id),
  reason text,
  recorded_by uuid,
  created_at timestamptz not null default now()
);
create index on app.employee_benefit (tenant_id, employee_id, effective_from desc);
```

**Por que tabela estreita e não colunas em `employee_compensation`:** a linha
larga forçaria uma vigência nova do pacote inteiro para mudar só o VR, e
`employee_compensation` já está aplicada — migration aplicada não se edita. Com
esta, a folha base é `salary + sum(amount) where composes_base`, e um tipo novo
de verba não exige migration.

### 1e. `dp_benefit_cycle` — a rotina mensal, um modelo para as duas

Cesta e VT são o mesmo objeto: um ciclo do mês que apura direito por pessoa com
um motivo. Um modelo, dois `kind` — não dois modelos paralelos.

```sql
create table if not exists app.benefit_cycle (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenant(id) on delete cascade,
  kind text not null check (kind in ('food_basket','transport_voucher')),
  period_year  smallint not null,
  period_month smallint not null check (period_month between 1 and 12),
  window_start date not null,          -- VT: 21 do mês anterior
  window_end   date not null,          -- VT: 20 do mês de referência
  business_days smallint,
  status text not null default 'draft'
    check (status in ('draft','generated','exported','cancelled')),
  generated_at timestamptz, generated_by uuid,
  created_at timestamptz not null default now(),
  unique (tenant_id, kind, period_year, period_month, status)
      deferrable initially deferred
);
```

`app.benefit_entitlement` é a linha por pessoa: `cycle_id`, `employee_id`,
`unit_id`, `entitled boolean`, `reason text`, `days_base`, `absences_prior`,
`net_days`, `unit_amount`, `round_trip_amount`, `total_amount`. As colunas de
dias ficam nulas para cesta — mesmo modelo, campos que não se aplicam vazios; é
mais barato que duas tabelas quase iguais.

**Regras de negócio, copiadas literalmente da tela (não reinventar):**

- VT: janela **21 → 20**; faltas injustificadas contadas no **mês civil anterior
  ao início do período**; `net_days = days_base − absences_prior`;
  `total_amount = net_days × round_trip_amount`.
- Cesta: perde o direito por **falta injustificada** ou **admissão depois do
  início do período**. O `reason` grava qual dos dois — a pessoa vai perguntar.
- Os dois leem `app.leave_period` com `category` de falta injustificada. **Essa
  leitura é financeira**: errar aqui tira dinheiro do colaborador. Merece o
  teste mais explícito da etapa.

Ciclo `generated` ou `exported` é imutável (regra 9): correção é ciclo novo com
`reason`, nunca `update`.

### 1f. `dp_unit_compliance` — laudos

```sql
create table if not exists app.unit_compliance_report (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenant(id) on delete cascade,
  unit_id   uuid not null references app.unit(id),
  type text not null,                       -- PCMSO, PGR, LTCAT+LTIP…
  valid_until date not null,
  notes text,
  document_id uuid references app.document(id),
  replaces_id uuid references app.unit_compliance_report(id),
  created_by uuid, created_at timestamptz not null default now()
);
create unique index on app.unit_compliance_report (tenant_id, unit_id, type)
  where replaces_id is null and valid_until is not null;
```

Renovar = inserir apontando `replaces_id` para a vigente — o mesmo padrão de
`app.document`. Situação (`EM DIA` / `A VENCER` / `VENCIDO`) é **derivada de
`valid_until`**, nunca coluna: coluna de status vence sozinha e ninguém percebe.

Sem domínio sensível: laudo é do local, não da pessoa. RLS por tenant e por
escopo de unidade (`util.can_see_unit`), como as demais tabelas de unidade.

### 1g. `dp_movement_period` — movimentação vira período

Hoje `app.workforce_movement` tem `unit_id`, `type` e `event_date`: é um
**evento**. O legado trabalha com **período** e projeta a unidade de atuação a
partir dele. Colunas aditivas: `origin_unit_id`, `destination_unit_id`,
`origin_work_post_id`, `destination_work_post_id`, `effective_from`,
`effective_to`.

A regra que a tela declara vira leitura derivada, não campo editável:

> unidade de atuação = destino da movimentação vigente (sem `effective_to`, ou
> com `effective_to` no futuro); na ausência de movimentação, a lotação de
> `app.employee.unit_id`.

Isso **fecha** um dos três campos que `SPEC-RH.md` §4 deixou "a confirmar com o
cliente". Não é decisão pendente: é comportamento observado em produção.

### 1h. `dp_leave_extension` — férias e atestado

`app.leave_period` ganha `document_id` (o anexo do atestado), `accrual_period`
(`2025/2026`) e `limit_date` (data limite de férias, admissão + 12 meses). Todas
anuláveis, todas aditivas. Sem coluna de diagnóstico — regra 10, nas três
camadas.

### 1i. `dp_payroll_code_map` — a curadoria que o P3 ia construir

```sql
create table if not exists app.payroll_code_map (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenant(id) on delete cascade,
  code text not null,
  description text,
  nature text not null,          -- espelha app.payroll_entry.nature
  category text,                 -- a classificação contábil que falta
  validated boolean not null default false,
  validated_by uuid, validated_at timestamptz,
  unique (tenant_id, code)
);
```

Semeia com `select distinct code, description, nature from app.payroll_entry` —
o cliente já classificou. A reunião com a contabilidade preenche `category` e
marca `validated`; **linha não validada não entra em indicador financeiro**,
mesma regra da curadoria de unidade.

### 1j. `dp_cadastral_fields`

`app.employee_pii` ganha `marital_status`, `race_color`, `education_level`,
`disability` (booleano — **não** o tipo de deficiência), `dependents_count`,
`dependents_names text[]`. `app.employee_position` já ganhou `level` e
`work_post_id` em 1c; ganha aqui `workload_minutes` e `shift_label` (a jornada
em texto livre do legado, `"10:00 AS 22:00 INT 14:30 AS 15:45"` — preservada
como texto até o Quadro de Postos cobrir todos, e então descontinuada).

`race_color` e `disability` são dado sensível: ficam sob o domínio `pii`, e
`disability` guarda só o booleano legal, nunca a condição.

### 1k. `dp_panel_views` — a superfície pública do painel

Duas RPCs em `public`, `security definer` com `search_path = ''`, e uma view:

- `public.fn_dp_panel(p_from date, p_to date, p_unit uuid default null,
  p_company uuid default null)` → os 9 KPIs de topo.
- `public.fn_dp_alerts()` → os 8 contadores do painel de alertas, com as janelas
  vindas de `app.document_type.expiry_alert_days` — não constantes no SQL.
- `public.vw_unit_compliance` (`security_invoker = on`) → laudos com situação
  derivada.

**A folha base é uma soma filtrada, e é o ponto crítico do painel:**

```sql
select sum(c.salary) + coalesce(sum(b.amount) filter (where bt.composes_base), 0)
```

⛔ **Parada obrigatória.** Coluna nova em view pública. E cuidado com a segunda:
`public.fn_dp_panel` agrega dado de `compensation`; devolve **agregado por
unidade/empresa**, nunca linha por colaborador. O card "unidades com sinistro
ativo" devolve **contagem**; o nome exige `compensation` e sai pelo caminho 2.

## 2. Backend (FastAPI — caminho 2)

Rotas novas sob `/dp`, todas com revalidação de papel e domínio:

- `GET /dp/postos`, `POST`, `PATCH` — Quadro de Postos.
- `GET /dp/beneficios/catalogo` · `POST /dp/beneficios/reajuste` — nova vigência
  de plano ou tarifa. **Nunca `PUT` no valor.**
- `POST /dp/ciclos` (kind, ano, mês) → apura e devolve **preview** sem gravar
  linha definitiva; `POST /dp/ciclos/{id}/gerar` → congela; `GET
  /dp/ciclos/{id}/export?formato=xlsx|pdf|banco`.
- `GET /dp/laudos`, `POST`, `POST /dp/laudos/{id}/renovar`.
- `GET /dp/rubricas`, `PATCH /dp/rubricas/{code}` — curadoria do mapa.
- `PATCH /dp/colaboradores/{id}/conta` — exige `banking`; responde **sempre
  mascarado**.

**Regra 10 do PRD, por construção:** o serializer de conta bancária vive num
único módulo (`operax/dp/banking.py`) e a única função que devolve o número
completo é a que monta o arquivo de remessa, que escreve em `bytes` e nunca em
resposta JSON. Teste: nenhuma resposta de rota contém `account` fora de máscara.

O apurador de ciclo e o validador de linha do import são a **mesma função** por
tipo — regra 1 do `PRD-RH.md` estendida às rotinas.

## 3. Telas

Segue a rodada 7 do Claude Design; especificação de comportamento apenas.

- **Painel de DP** — os 9 KPIs no topo, os 8 cartões de alerta e as listas
  correspondentes; raio-x de benefícios; consolidado por empresa. Filtro na
  query string, como o resto do produto.
- **Quadro de Postos** (Administração › Unidades) — lista por unidade, código,
  escala vinculada.
- **Benefícios** (Administração) — catálogo com abas por tipo e a ação
  **Reajuste**, que abre "nova vigência (desde, valor, motivo)". Sem lápis no
  valor vigente.
- **Ciclo mensal** — período, apuração, tabela por pessoa com `entitled` e
  `reason` visíveis, agrupamento por unidade, e os três botões de export. O
  botão de remessa só aparece para quem tem `banking`.
- **Laudos** (Unidades) — lista por unidade e situação, ação **Renovar** que
  cria registro novo. Sem campo de data editável na linha vigente.
- **Conta bancária** — campo dentro da aba de domínio `banking` na ficha, com
  máscara (`•••• 8723`) e edição por formulário próprio.

Visibilidade de aba por papel, sem cadeado e sem cinza — regra 5 do projeto.

## 4. Testes que fazem parte da entrega

**`make db-test`** (estruturais e de isolamento):

- `banking` existe no enum e a matriz semeada dá `true` só para owner,
  personnel e accounting.
- `hr` não lê `app.employee_bank_account`; `personnel` lê. Duas asserções.
- Nenhuma tabela desta etapa tem grant para `authenticated`.
- `unique (tenant_id, unit_id, code)` de `app.work_post` rejeita duplicata.
- Laudo renovado não deixa duas linhas vigentes para o mesmo (unidade, tipo).
- Ciclo `generated` recusa `update` — o gatilho falha alto.
- Supervisor de unidade vê os laudos da sua unidade e **zero** de outra.

**pytest:**

- Folha base: fixture sintética com salário, ajuda de custo, cargo de confiança,
  periculosidade e VR → o total inclui os três primeiros e **exclui** o VR.
  É a asserção que traduz o critério "bate na vírgula".
- VT: janela 21→20, faltas do mês civil anterior, `net_days` e total; casos de
  admissão e desligamento no meio do período.
- Cesta: perde por falta injustificada; perde por admissão após o início; o
  `reason` diz qual.
- Remessa: o arquivo contém a conta; **nenhuma resposta JSON de rota contém**.
- Mapa de rubrica: código não validado não entra em indicador.

**E2E:** gerar ciclo de VT → conferir por unidade → exportar Excel → renovar um
laudo e ver a situação virar `EM DIA` com o anterior no histórico.

## 5. Segurança e LGPD

- Quatro domínios sensíveis a partir daqui: `pii`, `compensation`, `health`,
  `banking`. `disciplinary` segue como estava.
- Conta bancária: máscara na tela, número só no arquivo, `audit_log` em toda
  leitura que monte remessa — quem gerou, quando, para qual ciclo.
- `race_color` e `disability` sob `pii`; `disability` guarda o booleano legal,
  jamais a condição.
- Dependentes são **nome de terceiro**: mesma proteção de `pii`, nunca em view
  pública, nunca em template que não seja do domínio.
- Diagnóstico, CID e restrição: sem coluna, sem campo, sem template. As três
  camadas negam, como na etapa de RH.
- Arquivo de remessa vai para storage privado do tenant com retenção declarada;
  nunca é servido por URL pública.
