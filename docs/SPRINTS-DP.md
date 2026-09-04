<!-- verificar-docs: inexistentes-de-proposito app.benefit_type app.employee_bank_account app.work_post public.fn_dp_panel public.fn_dp_alerts app.work_schedule_day -->
<!-- `app.work_schedule_day` entra aqui porque este documento REPORTA que ela não
     existe. O SPEC-DP a cita como existente e por isso segue vermelho lá — o gate
     está certo, e silenciá-lo no SPEC seria corrigir o teste em vez do desenho. -->

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

**Linha de reconciliação declarada:** como triênios não estão na fórmula do
legado, `OperaX − legado = total de triênios`. Diferença igual a esse total é
aprovação; qualquer outro valor reprova. Sem essa linha escrita, o gate reprova
por desenho e alguém "conserta" o número certo.

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
| S1 — Fundação | ⛔ **bloqueada** | `dp_work_post`, `dp_benefit_catalog` | — | 0 |
| S2 — Domínio `banking` | ⛔ **bloqueada** | `dp_banking_domain`, `dp_banking_account` | — | 0 |
| S3 — Ciclo mensal | pendente | `dp_benefit_cycle` | — | 0 |
| S4 — Painel e alertas | pendente | `dp_movement_period`, `dp_leave_extension`, `dp_cadastral_fields`, `dp_panel_views` | — | 0 |
| S5 — Laudos e rubricas | pendente | `dp_unit_compliance`, `dp_payroll_code_map` | — | 0 |

Onze slots, um arquivo por slot. ⛔ `dp_banking_domain` e `dp_banking_account`
são **arquivos separados**: o Postgres proíbe usar o valor novo do enum na mesma
transação que o adiciona, e cada migration roda em uma (SPEC §1a).

## ⛔ Por que nada foi despachado

Verificação de 04/09/2026, antes do primeiro despacho.

| # | Condição | Estado |
|---|---|---|
| 1 | Os quatro documentos no repositório | ⛔ **faltam `PRD-DP.md` e `ANEXO-COBERTURA-LEGADO-FASTPARK.md`** |
| 2a | FORCE em `app` | ⛔ **zero** — ver abaixo |
| 2b | A captura enxerga flags de segurança | ✅ sim: RLS, FORCE, policies, grants e revokes |
| 3 | Medição do §1d-bis | ✅ resolvida: `seniority_bonus` **sai da semente por ora** |
| 4 | Arquivos e critérios preenchidos | ✅ resolvido por este quadro |
| 5 | Sprint pedindo decisão fechada | ⚠️ **não verificável** sem o `PRD-DP.md` |
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

### O §1d-bis não pôde ser medido por dado, e a decisão veio do dono

`app.payroll_entry`, `payroll_event_map` e `payroll_period` têm **0 linhas em
produção**. Não há folha importada, então "existe rubrica de triênio separada do
salário?" não tem resposta empírica.

✅ **Decisão do dono em 04/09: `seniority_bonus` sai da semente por ora.** Os
demais tipos entram. A linha de reconciliação do gate de S1 muda junto: sem o
triênio na semente, `OperaX − legado` deixa de ser "o total de triênios".
**Reescrever essa linha é pré-requisito de despachar S1** — do contrário o gate
reprova por desenho, que é o que ela existia para evitar.

### 🔴 `app.work_schedule_day` não existe

A SPEC §0 (linha 26) cita `app.work_schedule_day` com as colunas
`entry_1 · exit_1 · entry_2 · exit_2` como algo que **já existe**, afirmando que
"falta o elo posto → escala, não a escala". Medido: a tabela **não existe em
produção nem no repositório**, e nenhuma tabela do banco tem essas quatro
colunas. O que existe é `app.schedule_rotation_map`.

⚠️ O `CLAUDE.md` §Convenções repete o erro, dizendo que `work_schedule_day` "já
existia antes deste modelo".

⛔ **S1 depende dessa premissa** (`work_post` vincula posto a escala). Se a escala
por dia não existe no domínio, o elo não tem ponta — e isso muda o escopo de S1,
não o resolve dentro dele.

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

## A pergunta do falso verde, aplicada aos gates existentes

Feita antes de aceitar cada conjunto. Resultado: **os gates do plano têm o
positivo** e não precisam de acréscimo.

- **S2** — *"`hr` recebe `permission denied`"* é só-negativo e ficaria verde num
  banco onde ninguém lê nada. ✅ O plano já traz *"`personnel` lê"* ao lado.
- **S4** — *"supervisor continua sem ver outra unidade"* idem. ✅ O guardião
  carrega o positivo *"e vê a dele"*.
- **S1, S3, S5** — os gates são de igualdade contra o legado (folha base, linha a
  linha, vigência única), que são positivos por construção.
