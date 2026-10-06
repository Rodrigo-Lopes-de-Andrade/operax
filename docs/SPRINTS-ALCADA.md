# OperaX — sprints da alçada de aprovação

Implementação de `DECISAO-ALCADA-APROVACAO.md`. **Só o orquestrador escreve
status neste arquivo.** Teto: dois ciclos de correção por sprint.

Revisão de toda sprint: `code-reviewer` **e** `guardiao-da-alcada`.

---

## A0 — Reconferência · ✅ 28/09/2026

Condições de parada verificadas antes do primeiro despacho:

| # | Condição | Resultado |
|---|---|---|
| 1 | Decisão no repositório | ✅ presente (ainda não commitada) |
| 2 | §2 bate com o repo | ✅ conferido nas **migrations**, não no dicionário: `justification` (05 + 23: `accepted/rejected`, default `accepted`, só `justification_read`/`_write`); `payroll_period` (07: `aberta/importada/conferida/fechada`, nunca traduzido); `deviation_event_unico_active` (05) e `_modo` (18), ambos `where status = 'active'`. Única deriva: o `on conflict` está em `regras.py:353`, não `:271` |
| 3 | Elenco | ✅ `fastapi-developer`, `nextjs-developer`, `code-reviewer`; `guardiao-da-alcada` criado nesta data |
| 4 | `make db-test` verde antes | ❌→✅ vermelho no verificador de docs **pela própria decisão** (linha 1 listava `app.justification.status`, que existe, e omitia `public.fn_revisar_justificativa`). Corrigido com autorização do Rodrigo; suíte verde em seguida |

---

## P0.1 — O motor não recria o julgado · ✅ aprovada 28/09 (ciclo 1/2) · `fastapi-developer`

Ciclos: 0/2. Entregue: `where not exists` de justificativa `accepted` (mesmo
`mode`, tipo via `deviation_event_id`) só no `DETECT_SQL` de `regras.py`;
teste em `scripts/teste_justificativa_sobrevive.py` (não `.sql`: um `.sql` só
alcançaria cópia do SQL do motor) registrado na suíte. Vermelho no passo 4
contra o HEAD, verde depois; pytest 1540, ruff limpo. A primeira rodada da suíte
caiu no verificador de docs por este arquivo (erro do orquestrador, não da
sprint — não conta ciclo).

⚠️ **Acoplamento com a P1.2:** a justificativa é imutável, então com a P1.1 ela
nasce `pending` e **continua** `pending` depois da aprovação — a aprovação é
linha em `app.justification_review`. O filtro da P0.1 (`status = 'accepted'`)
não enxergaria o aprovado pelo RH. A P1.2 tem de estender o filtro à revisão
`approved`, e o teste desta sprint tem de ganhar esse caso.
Achado lateral: nenhum código chama `revoke_deviation(..., 'justified')` — a rota
de justificativa só insere; o `justified` hoje só nasce à mão.

**`code-reviewer`, 28/09 — REPROVADO.** CRÍTICO: o `not exists` não filtra
`j_event.status`, e congela o evento `active` com justificativa aceita — o único
caminho que a rota produz hoje. Reproduzido com o SQL real: batida muda, o
controle vai a `active/150`, o justificado fica `active/40`. Também: revogado
que reaparece nunca volta; linha nova de `SUPERSEDED` fica congelada. Conserto:
`and j_event.status = 'justified'`. ALTO: quatro cláusulas do predicado
sobrevivem à mutação (`j.status`, `type`, `reference_date`, `tenant_id`) — o
teste precisa dos casos active-reescrito, rejected, outro tipo no mesmo dia e
outro dia. BAIXO: nome `.py`; CLAUDE.md não lista o passo novo.
**`guardiao-da-alcada`, 28/09 — APROVADO** (verificações 1 e 2 PASSA; 3–7
PENDENTE, dependem das P1). Vermelho no passo 4 reproduzido pelo guardião contra
o `regras.py` do HEAD num overlay; índices com o predicado original em
`pg_indexes`; produção: 6 com flag e 0 `no_punches`, 402 ativos sem flag. A
suíte caiu de novo no verificador de docs por este arquivo (erro do
orquestrador; exceções corrigidas e conferidas).

**Ciclo 1/2 despachado em 28/09** com o CRÍTICO e o ALTO do `code-reviewer`.
Entregue: `and j_event.status = 'justified'` no `not exists`; teste com os casos
(a)–(d); caso (a) vermelho contra o patch anterior e verde agora; mutações de
`j.status`, `j_event.status`, `type`, `reference_date` e `mode` derrubam o teste
(a de `tenant_id` não, e está documentado: `employee_id` implica o tenant).
Suíte, pytest 1540 e ruff verdes, segundo o desenvolvedor. Re-revisão
despachada aos mesmos dois revisores.

**`code-reviewer`, ciclo 1 — APROVADO.** Reprodução própria: aceita+active com
batida mudada dá `active/150` (era `active/40`); revogado que reaparece volta a
ser emitido. Sete mutações derrubam o teste. MÉDIO não bloqueante: trocar
`= 'justified'` por `<> 'active'` passa verde — falta o caso "revogado com
justificativa aceita reaparece" que o comentário de `regras.py` promete; entra
como reforço de teste depois do gate, não como ciclo. Dívida anterior registrada
para a §4: a justificativa fica presa ao id do evento, e o `SUPERSEDED` faz
`fn_pending_justification` mostrar o desvio como pendente de novo.

**`guardiao-da-alcada`, ciclo 1 — APROVADO.** Suíte completa verde na árvore
real; mutações refeitas por ele: HEAD reprova no passo 4 e cada cláusula
(`j_event.status`, `j.status`, `type`, `reference_date`, `mode`) é morta pelo
caso declarado; `indpred` dos dois índices intacto; produção 6 com flag / 0
`no_punches`.

**Fechamento, conferido pelo orquestrador em 28/09:** caso (e) acrescentado (aceita
sobre evento `revoked` → o fato volta); a mutação `<> 'active'` numa cópia
reprova em (e). Na árvore: `testar_migrations.sh` → `=== SUÍTE COMPLETA OK`;
pytest 1540; ruff limpo; prettier e tsc limpos; Vitest 1211/1211 (a primeira
rodada teve 1 falha sem mudança de frontend e as duas seguintes passaram —
instável, não desta sprint). Não commitado.

## P0.2 — Quem não bate ponto · ✅ já resolvida — sem despacho

**A §5.1 da decisão está desatualizada.** Medido em produção em 28/09/2026
(agregado, só leitura): `app.employee.exception_tracking` (migration 26, 26/08)
está `true` para os **6** supervisores, e eles têm **0** `no_punches` ativos em
qualquer período. `jornada.py:161` (`and not e.exception_tracking`) impede a
materialização da jornada, e `scripts/96_teste_jornada.py` já cobre o caso na
suíte. Nada a implementar; a verificação 2 do guardião confirma a cada sprint.
Resta **uma** candidata a exceção (matrícula 10), que é decisão pela tela de
Rotações, não desta etapa.

## P0.3 — `app.holiday` · ✅ aprovada 28/09 (ciclo 1/2) · `fastapi-developer`

Ciclos: 0/2. Entregue: migration `20260928235913_holiday_calendar.sql` (tabela,
policy aprovada literal, tipo `punch_on_holiday` + config por tenant);
`jornada.py` (discriminador `holiday_off` = semana fixa sem afastamento —
a rotação curada sai `manual_roster`, e o afastamento também sai
`secullum_schedule`, por isso `source` sozinho não serve); `regras.py` (tipo
novo só no CTE `evento`; P0.1 intacta); `revogacao.py` (`REASON_HOLIDAY`);
`dp/ciclo.py` (`holiday_worked` no VT); `motor/feriados.py` (carga nacional
com a Paixão, reprocessamento por dia, passo automático); router `/feriados`
só owner; `scripts/83_teste_feriado.py` (36 asserções, vermelho→verde em
etapas); 98 com 26 asserções novas, só acréscimos. Suíte verde na árvore real
depois de o orquestrador tirar `app.holiday` das exceções de docs.
⚠️ Para os revisores: (1) guarda `test_todo_join_do_apurador_propaga_o_tenant`
foi de 7 para 9 joins — alteração de asserção existente, que a própria mensagem
da guarda manda fazer; julgar se é enfraquecimento. (2) `holiday_owner` é
`for all` (inclui delete); o "sem delete" hoje depende só da ausência de grant.
⛔ Deploy: migration ANTES do push, senão os dois crons morrem em
`relation "app.holiday" does not exist`; com a carga feita, o
`operax-motor-retro` reprocessa o 07/09 sozinho. Escrita em produção — Regra 0.

**`guardiao-da-alcada`, 28/09 — REPROVADO (um item).** D: o negativo novo
`nem alcança linha para alterar (using)` do 98 não tem positivo — com
`holiday_owner` trocada por `using (... and false)` o 98 fica verde (provado num
clone do ensaio). Volta: o positivo do owner no `using`. Passam: suíte completa,
pytest 1574, ruff; oito mutações de jornada/VT/regras mortas pelo 83; negativo
municipal e positivo nacional; policy e grants iguais aos aprovados (o
`for all` não abre delete: authenticated sem grant, service_role sem DELETE —
mas o backend conecta como `postgres`, dono da tabela, então para ele o "sem
delete" é só código); guarda 7→9 joins não é enfraquecimento (duas mutações a
derrubam). Verificação 2b/2c PENDENTE: a leitura de produção do guardião foi
barrada pelo classificador de permissões — não contornada.

**`code-reviewer`, 28/09 — REPROVADO.** ALTO 1: o VT não tem prova — três
mutações do `_SCHEDULE_SQL` (`m.data = w.reference_date`, `desconsiderada`,
`hora is not null`) sobrevivem ao 83. ALTO 2: `run_late` refaz todo feriado de
[hoje-89, hoje-7] em toda passada, mudado ou não — dia de feriado fica vivo por
83 dias e o `SUPERSEDED` o devolveria ao relatório; limitar aos feriados
escritos recentemente (`updated_at`). ALTO 3: a ordem de deploy (migration
antes do push, depois a carga) só está neste arquivo; vai para o cabeçalho da
migration. MÉDIO: motivo de revogação errado ao desativar feriado; `GET
/feriados` sem teste de 403; `for all` em `holiday_owner`. BAIXOS: `dow is not
null` sem caso, `ano` sem limite (500), auditoria do update com `antes` nulo,
`name` sem strip, docstring divergente.

**Decisão do dono, 28/09: separar `holiday_owner` em insert e update** (sem
trigger de delete). Mudança de policy autorizada; estreita o que já foi
aprovado.

**Ciclo 1/2 despachado em 28/09** com o D do guardião e os itens acima.
Entregue: positivo do owner no `using` (98); três casos de VT (folga no feriado
e bate noutro dia; só desconsiderada; só coluna sem hora) com as três mutações
mortas; `run_late` restrito a `updated_at >= relógio do tenant − 2 dias`
(antigo inalterado não é refeito; desativado agora é); bloco ⛔ de ordem de
deploy no cabeçalho da migration; `holiday_owner_insert` + `_update` (o `do $$`
exige exatamente 3 policies e reprova DELETE/ALL/`is_admin`); motivos
`REASON_HOLIDAY_REMOVED` e `REASON_DAY_OFF_TO_HOLIDAY`; 403 no GET; BAIXOS.
Segundo o desenvolvedor: suíte verde na árvore real, 83 com 44 asserções,
pytest 1585. Re-revisão despachada.

**`code-reviewer`, ciclo 1 — APROVADO.** Mutações refeitas por ele: as três do
VT, `dow is not null`, `_require_owner` no GET, o filtro `updated_at`, `since`
em UTC e o pulo do incremental — todas morrem. 07/09 corrigido pela primeira
carga se o retro rodar em até 48 h; saída manual existe. Catálogo com
exatamente três policies. BAIXO restante: `REASON_HOLIDAY_REMOVED` também sai
quando o dia virou afastamento ou revezamento com o feriado ativo (raro).

**`guardiao-da-alcada`, ciclo 1 — APROVADO.** Suíte completa verde na árvore
real (pytest 1585, 83 com 44); `using ... and false` no update, `for all` e
policy de delete reprovam no 98 e no `do $$`; as três mutações de VT morrem;
98 só com acréscimos. 2b/2c seguem PENDENTE (leitura de produção barrada ao
guardião; liberação do dono).

⚠️ **Os crons de produção rodam `--modo=producao`** (conferido no Railway em
28/09: `operax-motor` e `operax-motor-retro`), ao contrário do que o CLAUDE.md
diz ("sombra até o falso positivo ≤ 5%"). Nenhum alerta sai (o sender pergunta
o G4 ao banco), mas o painel mostra indício de produção. Fora desta etapa;
levado ao dono. Consequência aqui: o reprocessamento manual do 07/09 é
`--modo producao`, não `sombra`.

---

## Onda P0 — ✅ fechada no código em 28/09. Nada commitado, nada em produção.

Ciclos: 0/2. Nada em `supabase/migrations/` (parada: tabela nova com policy).

**A §5.2 da decisão está invertida — medido em produção em 28/09 (agregado):**
o motor não conhece feriado. `jornada.py` materializa o feriado como `work`, e
`punch_on_day_off` só dispara em `day_off` (`regras.py`). Em 07/09/2026
(Independência, segunda) foram **64** `no_punches` ativos contra **8–10** nas
segundas 31/08, 14/09 e 21/09; `punch_on_day_off` = 0 nas quatro; e
`expected_workday` não tem `holiday` em nenhuma. O feriado gera ~55 faltas
falsas, não trabalho-em-folga. Próximas: 12/10 e 02/11 (segundas).

Desenho proposto: tabela única, `unit_id` nulo ⇔ nacional, uma linha por
unidade para estadual/municipal (a unidade não tem cidade/UF/IBGE em lugar
nenhum); consumo só em `jornada.py` (afastamento > feriado > escala), sem tocar
`regras.py` nem o grão. Policy: padrão Caminho 2 da DP — sem grant a
`authenticated`, sem delete (desativa com `active = false`).

**Decisões do dono, 28/09/2026:**
- **Escala:** depende de quem opera. Quem opera em feriado segue a escala (faltar
  é falta); quem não opera folga. Exige sinal novo "opera em feriado".
- **Trabalhar em feriado é indício.**
- **VT:** quem trabalhou no feriado recebe o VT do dia; quem folgou não.
- **Quem escreve o calendário:** só `owner`.
- **Sexta-feira da Paixão** entra na carga nacional.
- **Indício já em relatório é revogado** quando o feriado chega depois.

**Desenho v2 (28/09)** propôs o sinal por unidade (tabela nova de 24 decisões,
policy só-owner), tipo novo `punch_on_holiday`, `holiday_worked` no VT,
`REASON_HOLIDAY` e reprocessamento por data para feriado cadastrado com atraso.

**Medido em produção em 28/09 (agregado) — o sinal NÃO é por unidade:**

| origem da jornada | 31/08 | 07/09 | 14/09 |
|---|---|---|---|
| `secullum_schedule` (escala semanal) | 54/62 bateram | **1/63** | 57/65 |
| `inferred` (revezamento) | 5/9 | **5/8** | 3/8 |

Em todas as unidades o pessoal de escala semanal folgou e o de revezamento
trabalhou. Sinal por unidade transformaria em falta a folga legítima da escala
semanal. Recomendação a confirmar com o dono: o feriado é folga para jornada de
escala semanal e não altera jornada de revezamento — **sem tabela de operação**.

**Decisões do dono sobre o v2, 28/09/2026:**
- **O sinal é o tipo de escala, não a unidade.** Feriado é folga para jornada de
  escala semanal do Secullum; jornada de revezamento/inferida segue a escala.
  Sem tabela de operação.
- **Revezamento que trabalhou no feriado não gera indício.** `punch_on_holiday`
  só para escala semanal que bateu.
- **Policy de `app.holiday` aprovada** (parada cumprida): leitura por quem
  enxerga o tenant e, na linha de unidade, a unidade; escrita só `owner`; sem
  delete (`active = false`); fora do PostgREST, escrita pelo backend.

Perguntas originais (respondidas acima): (1) no feriado a escala de quem trabalha
continua valendo? (2) trabalhar em feriado é indício? (3) VT — `dp/ciclo.py`
conta dia pago por `day_type = 'work'`, e o feriado cortaria o VT de quem
trabalhou; (4) quem escreve o calendário — `is_admin` (inclui RH) ou só
`owner`? (5) Sexta-feira da Paixão no seed nacional? (6) indício já em
relatório é revogado quando o feriado chega depois? E o risco: a revogação só
olha 7 dias, então o 07/09 não se corrige sozinho.

## P1.1 — `pending` e a trava do espelho · ✅ aprovada 29/09 (ciclo 1/2) · `fastapi-developer`

Ciclos: 0/2. Medido em 28/09: produção tem **zero** linhas em
`app.justification`; o único escritor é `motor/justificativa.py`, que passa
`status` explícito — trocar o default não o afeta.

Entregue: migration `20260929010543_alcada_justification_pending.sql` (domínio
com `pending`, default `pending`, check `justification_espelho_nao_pende`, sem
`update`); `scripts/82_teste_justificativa_pendente.py` (A: trava do espelho com
positivos; B: estado da 23 reconstruído, migration real aplicada duas vezes por
cima) registrado na suíte. **Conferido pelo orquestrador em 29/09:** o bloco B
caía localmente — `\i <caminho do host>` não é visto pelo wrapper de psql;
passou a embutir o texto do arquivo real (única alteração do orquestrador). Na
árvore: `=== SUÍTE COMPLETA OK`, pytest 1585, ruff, prettier e tsc limpos.
Revisão despachada a `code-reviewer` e `guardiao-da-alcada`.

**`guardiao-da-alcada`, 29/09 — APROVADO.** Suíte completa verde na árvore
real; verificação 1 PASSA (teste importa `regras.DETECT_SQL`; `indpred` dos dois
índices intacto); 2 PASSA (produção: 6 com flag, 0 `no_punches` deles, 403 de
quem não tem a flag); 3 PASSA (check recusa `secullum/pending` no banco,
`operax/pending` entra; migration sem `update`). Mutações numa cópia: `update`
retroativo pego pela guarda estática; o mesmo `update` escrito
`"app".justification` escapa da regex e é pego pela prova viva do bloco B;
trava trocada por `check (true)` reprova. 4–7 PENDENTE (dependem da P1.2).

**`code-reviewer`, 29/09 — REPROVADO (um ALTO).** Gate §8 cumprido; seis
mutações da migration morrem; a troca de `\i` por `read_text()` não enfraquece a
prova. ALTO: **a premissa "único escritor" é falsa** — `supabase/seed.sql:561`
grava `app.justification` sem `status`; com o default novo, a justificativa
semeada sobre evento `justified` nasce `pending`, o filtro da P0.1 deixa de
enxergá-la e `make motor` no ambiente semeado recria o desvio julgado
(confirmado pelo orquestrador: seed, `motor/justificativa.py` e um mock de teste
são os únicos). BAIXOS: docstrings que negam o estado pendente (`models.py`,
`motor/justificativa.py`, `justification-verdict.tsx`); a 23 não é mais
reaplicável à mão por cima da P1.1 (não editar a 23 — `db push` é
transacional; registrar no runbook). Dívida para a P1.2: `employees.py`
lista justificativas sem status.

**Ciclo 1/2 despachado em 29/09** com o ALTO, a premissa no cabeçalho da
migration e as docstrings. Entregue: `seed.sql` grava `status = 'accepted'` e o
`do $$` final reprova evento `justified` sem justificativa `accepted` (vermelho
"15 evento(s)" sem o conserto, verde com ele, num banco próprio com o stub de
auth complementado — não é `supabase db reset` completo); cabeçalho da
migration com os dois escritores (SQL inalterado); docstrings de `models.py` e
`motor/justificativa.py`; a do `justification-verdict.tsx` aplicada pelo
orquestrador (fora da fronteira do desenvolvedor). Suíte verde na árvore real.
Re-revisão despachada aos dois revisores.

**`guardiao-da-alcada`, ciclo 1 — APROVADO.** Suíte verde; 1, 2(a) e 3 PASSA;
SQL executável da migration idêntico (só comentário mudou). Seed aplicado num
banco descartável: `justified_sem_aceita = 0`; com o conserto desfeito numa
cópia, a asserção reprova ("15 evento(s)"). 2(b)/(c) barrado pelo classificador
desta vez — **o orquestrador os dá por medidos nesta sprint**: o gate da
primeira entrega os rodou em 29/09 (6 / 0 / 403) e o ciclo não toca motor nem
produção. Observação: a suíte **não executa** `supabase/seed.sql`; regressão
como a deste ciclo só aparece em `supabase db reset`.

**`code-reviewer`, ciclo 1 — APROVADO.** Prova do seed refeita em banco
próprio (vermelho "15 evento(s)" sem o conserto, verde 15/15 com ele,
idempotente); nenhum outro escritor sem `status` (grep: rota, prova da 23,
testes que omitem de propósito; nada em `supabase/functions/` nem `e2e`); suíte
em banco próprio verde; pytest 1585. BAIXO (docstring de
`tests/test_justificativa.py`) corrigido pelo orquestrador.

**Fechamento, 29/09:** não commitado, nada em produção. A migration entra em
produção junto do lote da etapa (Regra 0).

⛔ **Para a P1.2, parada de contrato de API:** `POST /ocorrencias/{id}/justificativa`
deixa o cliente escolher `accepted`/`rejected` (`request.status`), então quem
enxerga o colaborador grava justificativa já aceita — é o contorno que a alçada
precisa fechar, e fechá-lo muda a interface pública.

## P1.2 — Revisão e RPC · ✅ aprovada 29/09 (ciclo 1/2) · `fastapi-developer` + `nextjs-developer`

Ciclos: 0/2.

**Decisões do dono, 29/09/2026 (paradas cumpridas):**
- **Contrato:** `POST /ocorrencias/{id}/justificativa` grava **sempre**
  `pending`; `status` sai do corpo. O supervisor explica, o RH decide pela RPC.
- **Policy e RPC aprovadas como na §4.2/§4.3:** `app.justification_review` com
  `review_read`, sem policy de escrita; `public.fn_revisar_justificativa` com
  `grant execute to authenticated` escrito na migration.
- **`app.revoke_deviation` perde o grant a `authenticated`** nesta sprint, com
  asserção negativa no 98.

**Primeiro despacho parou, corretamente, antes de escrever código:** não existe
ligação colaborador ↔ usuário no schema (`tenant_member` não tem
`employee_id`, `employee` não tem `user_id`; conferido pelo orquestrador), então
"o desvio de quem é `hr` é aprovado pelo `owner`" não tinha como virar código
sem heurística.

**Decisão do dono, 29/09: marca no colaborador.** Coluna em `app.employee`
(ex. `approval_owner_only boolean not null default false`), no padrão de
`exception_tracking`: desvio de colaborador marcado só o `owner` revisa. Cobre
também o RH aprovando o próprio desvio. Curadoria manual — RH novo sem a marca
cai na regra comum.

**Trilha de frontend entregue, 29/09 (`nextjs-developer`):**
`justification-verdict.tsx` envia só `{text}`, "Enviar justificativa", e a
confirmação diz que foi para aprovação do RH. A salvaguarda de ação
irreversível foi mantida e o JSDoc reescrito. O teste do componente foi
reescrito com 6 casos; o do corpo sem `status` reprova contra a versão antiga.
No `occurrence-drawer.tsx` mudou só o comentário. Nenhum E2E depende do fluxo.
Vitest 1212, prettier e tsc verdes, segundo o desenvolvedor. O nome
`JustificationVerdict` ficou por cirurgia.

**Trilha de backend entregue, 29/09 (`fastapi-developer`):** migration
`20260929114738_alcada_justification_review.sql`, com:
- `app.justification_review` conforme a §4.2: `grant select` para
  `authenticated` e `service_role`, só a policy `review_read`;
- `public.fn_revisar_justificativa`, com as seis recusas mais `owner_only`,
  cada uma via `raise ... P0001`;
- `app.employee.approval_owner_only`;
- `revoke execute` de `app.revoke_deviation` para `public, anon, authenticated`.
  O `public` é necessário porque a 11b deixou o acesso vir por herança de
  PUBLIC. `service_role` perde junto, e produção já estava assim;
- `fn_pending_justification` com a mesma assinatura: a justificativa pendente
  sem revisão sai da fila, e a reprovada volta.

Também mudaram:
- o `regras.py`, que passa a reconhecer a revisão `approved`;
- a rota, que grava `pending` com `extra="forbid"`;
- os testes: `teste_justificativa_sobrevive` (f/g/h), o 98 (+390 linhas, só
  acréscimos), o 92 e o pytest.

`CORPOS_FROUXOS` perdeu a rota, como a guarda manda.

Decisões onde o desenho deixava margem:
- **Papel checado antes de tudo.** `not_hr` = sem `hr`/`owner` em nenhum
  tenant. Justificativa de outro tenant vira `justification_not_found`, para não
  vazar que o id existe.
- **`owner_only` é código próprio.**
- **Competência de destino:** a migration 07 **não** impede duas abertas. A
  revisão vai para a mais antiga aberta entre os meses 1 e 12.

Vermelho→verde de (g) contra o `regras.py` anterior. Mutações feitas pelo
desenvolvedor, todas mortas: 3 do `regras.py`, 13 da migration e 2 da rota.
Com isso a suíte, o pytest (1589) e o ruff passaram. Conferido pelo
orquestrador na árvore real, depois de tirar das exceções de docs os objetos
que passaram a existir.

⚠️ **Sem caminho para marcar `approval_owner_only`:** nenhuma rota nem tela;
hoje é SQL de operador. Rota futura tem de exigir `owner`, não `is_admin`.

⛔ **Três contornos da alçada no banco, levados ao dono (parada: policy/grant):**
1. `justification_write` deixa `authenticated` inserir `status='accepted'`
   direto.
2. `deviation_write` (`is_admin`, inclui `hr`) deixa mover o desvio para
   `justified` por UPDATE.
3. `employee_write` (`is_admin`) deixa o `hr` zerar a própria
   `approval_owner_only`.

Os três só são alcançáveis por código rodando como `authenticated`, porque
`app` está fora do PostgREST.

Dívida: aprovar uma justificativa cujo evento não está `active` (revogado ou
`SUPERSEDED`) grava a revisão e não move nada, sem avisar.

Revisão despachada a `code-reviewer` e `guardiao-da-alcada`.

**`guardiao-da-alcada`, 29/09 — APROVADO.** Suíte completa verde em banco
próprio.
- **Verificações 1 a 6:** todas PASSA.
  - 1: casos f/g/h verdes. A mutação que remove o ramo da revisão reprova em (g).
    Índices intactos.
  - 2: produção 6 / 0 / 403.
  - 4: `not_hr` para o supervisor, `hr` passa, `anon` sem EXECUTE.
  - 5: `already_reviewed`, com contagem 1.
  - 6: com trigger temporária que lança erro, ficam 0 revisões e o desvio segue
    `active`. Sem ela, 1 revisão e `justified`. A reprovada volta à fila e a
    aprovada não.
- **Regra do dono:** `owner_only` para `hr` e o `owner` passa no colaborador
  marcado; `hr` passa no não marcado.
- **`app.revoke_deviation`:** ACL `{postgres=X/postgres}`; o supervisor recebe
  `permission denied`.
- **Arquivos protegidos:** 98 só com acréscimos, 99 intacto.
- **7:** PENDENTE (P1.3).

**`code-reviewer`, 29/09 — REPROVADO (um ALTO).** O gate da §8 passa no ensaio.
Suíte em banco próprio verde, com 37 asserções da alçada no 98; pytest 1589;
Vitest 1212; lint limpo. Mutações:
- 7 de 10 da RPC e da fila morrem;
- 5 de 5 do `regras.py` morrem.

- **ALTO-1:** nada no repositório produz `payroll_period.status = 'aberta'`.
  **Conferido pelo orquestrador:** o único escritor é
  `imports/repository.py:140`, que grava `'importada'`. Com dado real a RPC
  recusa toda aprovação com `no_open_period`: a justificativa sai da fila do
  supervisor e ninguém a aprova. Decisão do dono.
- **MÉDIO-1 (rollout):**
  - backend sem a migration da P1.1 → 500 em todo POST de justificativa;
  - frontend antigo com backend novo → 422.

  Ordem obrigatória: migrations P1.1+P1.2 → push do backend → `vercel promote`.
- **MÉDIO-2:** o filtro `month between 1 and 12` não tem teste (a mutação
  sobrevive).
- **MÉDIO-3:** a RPC não confere `j.status`: uma `accepted` legada pode ser
  "reprovada" sem efeito, e uma `rejected` legada pode ser aprovada. Consertar
  muda o contrato da RPC → dono.
- **MÉDIO-4:** os três contornos no banco. Nenhum torna o gate falso.
- **BAIXOS:**
  - `for update` antes do papel: oráculo por tempo, e a mutação sem o lock
    sobrevive;
  - a RPC não grava `audit_log` (declarar a revisão como trilha);
  - o autor pode aprovar a própria justificativa (segregação → dono);
  - uma linha longa no drawer.

**Decisões do dono sobre a reprovação, 29/09/2026 (paradas cumpridas):**
- **ALTO-1:** a revisão vai para a competência **não fechada** mais antiga
  (`status <> 'fechada'`, meses 1–12). `aberta`, `importada` e `conferida`
  recebem; o import não muda.
- **MÉDIO-3:** a RPC recusa justificativa que não está `pending` — recusa nova
  e nomeada (muda o contrato da RPC, autorizado).
- **Segregação:** o autor não revisa a própria justificativa — recusa nova
  quando `author_user_id = auth.uid()` (autor nulo não bloqueia).
- MÉDIO-4 (os três contornos no banco) segue com o dono; fora deste ciclo.

**Ciclo 1/2 despachado em 29/09** com ALTO-1, MÉDIO-2 (teste do filtro de
mês), MÉDIO-3, a segregação e o BAIXO do lock antes do papel.

Entregue no ciclo 1 (`fastapi-developer`), migration editada no lugar (nunca
aplicada): competência `status <> 'fechada'`; recusas novas `own_justification`
e `not_pending`; o lock saiu do começo — `not_hr`, depois leitura sem lock do
`tenant_id` e `justification_not_found`, só então `for update`. Ordem final:
`not_hr`, `justification_not_found`, `own_justification`, `owner_only`,
`already_reviewed`, `source_is_mirror`, `not_pending`, `no_open_period`,
`rejection_needs_reason`. O `not_pending` fica depois do `source_is_mirror`
porque espelho nunca é pendente (check da P1.1) e o tornaria inalcançável.
98 com 19 asserções novas (só acréscimos); `scripts/81_teste_revisao_concorrente.py`
novo (duas sessões reais: prova o lock e a ausência de espera para quem não
alcança). 12 mutações, todas mortas (a sem `for update` só pelo 81).
**Conferido pelo orquestrador na árvore real:** `=== SUÍTE COMPLETA OK` com o 81
rodando, pytest 1589, ruff limpo. ⚠️ `DECISAO-ALCADA-APROVACAO.md` §4.3 ainda
lista seis recusas e `aberta` — o texto certo é o cabeçalho da migration.
Re-revisão despachada.

**`guardiao-da-alcada`, ciclo 1 — APROVADO.** Suíte completa verde (o 81
rodou); 1, 2(a), 3, 4, 5 e 6 PASSA com a ordem nova (lock provado fora da frente
do papel pelo 81; `not_pending` e `own_justification` com positivos; `conferida`
e `importada` recebem, `fechada` e mês 13 não; outro tenant recebe
`justification_not_found`, não `not_pending`). 98 com `529 0` no numstat, 99
intacto, policies e ACLs iguais ao gate anterior. 2(b)/(c) barrado pelo
classificador — **o orquestrador os dá por medidos**, como na P1.1: o ciclo não
toca motor nem produção, e a última leitura foi 6/0/403. 7 PENDENTE (P1.3).

**`code-reviewer`, ciclo 1 — APROVADO.** Suíte em banco próprio verde (81
7/7), pytest 1589, Vitest 1212, lint limpo. 13 mutações próprias, todas mortas
(inclui `between 1 and 13`, `in ('aberta','importada')`, `not_pending` só para
`rejected` e sem a checagem de papel no tenant da linha). A leitura sem lock do
`tenant_id` não abre corrida (`authenticated` não tem UPDATE em
`app.justification`); a ordem não vaza entre tenants. MÉDIO: §4.3 da decisão
desatualizada — **corrigida pelo orquestrador em 29/09**. BAIXOS, como dívida:
falta `if not found` depois do `for update` (linha sumida por cascade cai no FK,
`23503`, não silencioso); a asserção "a sessão 2 ficou esperando" do 81 passa
sem o `for update` — quem mata o mutante é a seguinte.

**Fechamento da P1.2, 29/09:** ✅ aprovada (ciclo 1/2). Não commitada, nada em
produção. Seguem com o dono: MÉDIO-4 (três contornos de policy/grant), a
ordem de rollout do MÉDIO-1 e o aprovado sobre evento não `active`.

✅ Pergunta aberta 1 respondida pelo dono em 28/09: **o desvio de quem tem papel
`hr` é aprovado pelo `owner`**; o resto, pelo RH.

## P1.2b — As brechas no banco · ✅ aprovada 01/10 (ciclo 1/2) · `fastapi-developer`

**Decisão do dono, 29/09/2026 (parada de policy/grant cumprida): revogar a
escrita.** `authenticated` perde INSERT em `app.justification`, UPDATE em
`app.deviation_event` e INSERT/UPDATE/DELETE em `app.employee`; as policies de
escrita (`justification_write`, `deviation_write`, `employee_write`) saem.
Medido pelo orquestrador em 29/09: nenhum escritor dessas três tabelas roda
como o usuário — rota de justificativa, curadoria (`ALLOCATE_SQL`,
`EXCEPTION_SQL`), `rh/employees.py`, `rh/repository.py` e `alertas/ciclo.py`
autorizam no `user_scope` e gravam no `tenant_scope`; motor e Edge Functions
conectam direto. O 98 só grava nelas no preparo, como `postgres`. Despacho
depois do backend da P1.3, porque os dois mexem no 98 e na suíte.

**Entregue, 30/09 (`fastapi-developer`), sem parada:** migration
`20260930225115_alcada_revoke_writes.sql` — `drop policy if exists` das três e
`revoke` de INSERT (justification), UPDATE (deviation_event) e
INSERT/UPDATE/DELETE (employee) de `authenticated`; o `do $$` reprova privilégio
de escrita em tabela ou coluna, SELECT perdido, policy restante ou lista de
policies diferente de `*_read`. Grep dos escritores refeito: premissa
confirmada. Leitura de `app.employee` idêntica — `employee_write` tinha o mesmo
`using` do primeiro termo de `employee_read` (OR de permissivas), e as contagens
por RLS de 7 usuários × 3 tabelas não mudam. 98 só com acréscimos: estruturais,
21 de paridade de leitura e negativos que exigem `permission denied for table`
(não só 42501). 13 mutações, 12 mortas; M13 (tirar `is_admin` de
`employee_read`, fora do escopo) sobrevive porque a fixture não separa as
policies. Comentários de código e `docs/COBERTURA-ESCOPO.md:72` corrigidos.
Policies: 121 → 118.

**Conferido pelo orquestrador na árvore real, 30/09** (com os reforços da P1.3
juntos): `=== SUÍTE COMPLETA OK`, pytest 1636, ruff limpo, Vitest 1295/1295,
prettier e tsc limpos. Revisão despachada.

**`guardiao-da-alcada`, 30/09 — APROVADO.** Suíte verde em banco próprio.
Catálogo comparado entre um banco sem e outro com a migration (`relacl`,
`attacl`, `proacl`, `nspacl`, `pg_policies`, `pg_default_acl` de seis schemas):
só saem as três policies de escrita e caem os privilégios de escrita de
`authenticated` nas três tabelas; SELECT e `service_role` iguais. Os três
contornos passam no banco sem a migration e recebem `permission denied` com
ela. O caminho legítimo continua: `record_verdict` real grava `pending` e a RPC
como `hr` aprova e move o desvio. 1, 2(a), 3–7 PASSA; 98 `1041 0`, 99 intacto.
2(b)/(c) barrado — dado por medido (a sprint não toca motor nem
`exception_tracking`).

**`code-reviewer`, 30/09 — REPROVADO (por defeito fora da sprint).** A P1.2b e
os reforços da P1.3 estão certos e medidos: grants e policies, leitura de
`employee` idêntica (contagens do 98 conferidas contra um banco sem a
migration), 5 mutações do `do $$` e os negativos exigindo a mensagem de grant;
uma conexão por rota; premissa do `user_clock` sustentada; motor intocado pelo
reforço; `rows={[]}` morre no front.
- **CRÍTICO (da P0.3), confirmado pelo orquestrador:** em
  `motor/deteccao.py`, o parâmetro novo `scope` de `detect()` é sobrescrito
  por `async with tenant_scope(context) as scope` — o `TenantScope` vai como
  parâmetro SQL e todo `detect()` quebra (`cannot adapt type 'TenantScope'`):
  crons, retro e reprocessamento de feriado. Nenhum teste chama `detect()`
  contra banco. Não commitado nem em produção — o push quebraria o motor.
  Conserto despachado ao `fastapi-developer` (renomear para `run_scope` e teste
  real de `detect()`).
- **ALTO, parada do dono — quarto contorno:** `tenant_member_admin` (migration
  02) é `for all using util.is_admin(tenant_id)`, e `authenticated` tem
  INSERT/UPDATE/DELETE em `app.tenant_member`: o `hr` se promove a `owner`
  (passa por cima do `owner_only`) e o `personnel` se promove a `hr` e aprova.
  Medido pelo revisor numa transação desfeita. `app.user_scope` tem o mesmo
  desenho. Grep do orquestrador: nenhum código grava nas duas; só testes, como
  `postgres`. O cabeçalho da migration da P1.2b promete mais do que entrega.
- BAIXOS: o "antes" do catálogo no 98 tem `is_admin` escrito à mão; a contagem
  de policies diverge na base (−3 igual).

**Decisão do dono, 30/09 (parada de policy/grant cumprida): revogar a escrita
de `authenticated` em `app.tenant_member` e `app.user_scope`** e remover as
policies de escrita, na mesma migration da P1.2b (não aplicada). Ciclo 1/2
despachado com isso e o cabeçalho corrigido.

**Conserto do CRÍTICO, 01/10 (`fastapi-developer`):** o parâmetro virou
`run_scope` (`deteccao.py`, `feriados.py:162`, `test_feriados.py`, que trocava
`detect` por um falso e por isso nunca o pegou). `scripts/79_teste_detect_run.py`
novo, registrado na suíte: chama `detect()` e `feriados.reprocess` de verdade
num tenant próprio e confere `app.detection_run` (`incremental`, `backfill`,
`run_scope` explícito, reprocessamento). Código antigo numa cópia: 4 falhas
(`cannot adapt type 'TenantScope'`); atual: 12/12. Sombreamento reintroduzido e
`run_scope` ignorado: mortos. Varredura por AST em `motor/`: nenhum outro
sombreamento do mesmo tipo.

**Ciclo 1/2 da P1.2b entregue, 01/10:** grep sem escritor de aplicação em
`tenant_member` nem `user_scope`; `tenant_member_admin` e `escopo_admin` saem e a
escrita de `authenticated` é revogada nas duas; o `do $$` cobre as cinco
tabelas; leitura idêntica (`tenant_member_read` e `escopo_read` já contêm o que a
policy `for all` dava), medida por 7 usuários; 98 com seção nova (estruturais,
14 de paridade, negativos com a mensagem de grant: `hr`→`owner`,
`personnel`→`hr`, inserir membro, mexer em escopo), numstat `1249 0`; 19
mutações mortas pelo 98 e pelo `do $$`. Cabeçalho reescrito: diz o que a
migration garante e o que ainda depende de código (escrita por `tenant_scope`,
outras tabelas de `app` com escrita de admin). Policies 121 → 116.

**A suíte inteira estava vermelha por uma asserção fora da etapa:** `A4-f8` do
`scripts/97_teste_assistente.sql` comparava "a semana corrente" com o mês
corrente e reprova sempre que a semana cruza a virada do mês (hoje até 05/10).
Corrigida pelo orquestrador: compara com a soma bruta dos dry runs desde
`date_trunc('week', now())`, que é a janela da função para `p_weeks = 0` — a
prova de "nunca tudo" continua, sustentada pelo T3 (20 semanas atrás; o T2 cai
dentro da semana quando ela cruza o mês, como em 01/10).

**Conferido pelo orquestrador na árvore real, 01/10:** `=== SUÍTE COMPLETA OK`
(com o 79 e a seção nova do 98), pytest 1636, ruff limpo, Vitest 1295/1295,
prettier e tsc limpos. Re-revisão despachada.

**`guardiao-da-alcada`, ciclo 1 — APROVADO.** Suíte verde em banco próprio.
Catálogo sem × com a migration: saem exatamente as cinco policies de escrita e
os privilégios de escrita de `authenticated` nas cinco tabelas; `attacl`,
`proacl`, `nspacl` e `pg_default_acl` iguais; SELECT continua. Sonda das três
escaladas: aceitas sem a migration, `permission denied` com ela; leitura igual.
Caminho legítimo com as funções reais das rotas (`record_verdict` como
supervisor, `review_justification` como `hr`): `pending` → revisão `approved` →
desvio `justified`. 1, 2(a), 3–7 PASSA; `run_scope` sustentado pelo 79 (o
`teste_justificativa_sobrevive` roda o `DETECT_SQL`, não o `detect()`). 98
`1249 0`, 99 intacto; A4-f8 do 97 não enfraquecida. 2(b)/(c) barrado, dado por
medido. Furo de ambiente registrado: o `_baseline.sql` não tem
`auth.users.raw_user_meta_data`, então a suíte não exercita o `INSERT_SQL` da
rota de justificativa.

**`code-reviewer`, ciclo 1 — APROVADO.** Suíte em banco próprio, pytest 1636,
Vitest 1295, lint limpos. `detect()`: sombreamento, `run_scope` ignorado e
`feriados` sem `run_scope` morrem no 79 (`test_feriados` também mata dois, mas
só por `.venv/bin/pytest` — `python -m pytest` em `backend/` importa a árvore
real). Quarto contorno: grep sem escritor; leitura idêntica por definição e
medida num clone com as duas tabelas devolvidas ao estado anterior; negativos
morrem um a um (inclusive `personnel`→`hr` isolado); 7 mutações de catálogo
contra o 98 e 5 contra o `do $$` mortas; idempotente; cabeçalho conferido
contra o que a RPC lê. A4-f8: sem `greatest` e "tudo quando ≤ 0" morrem; verde
fora da virada. BAIXOS: só `p_weeks = 0` é testado (negativo não); "é a semana
corrente" depende da data (falta um dry run na semana anterior); `is_admin` à
mão no "antes" do 98; o 79 roda num tenant sem colaborador.

**Fechamento da P1.2b, 01/10:** ✅ aprovada (ciclo 1/2), com o conserto do
`detect()` (P0.3) e a correção da A4-f8. Não commitada, nada em produção.

## P1.3 — Fila e filtros · ✅ aprovada 30/09 (ciclo 1/2) · `fastapi-developer` (depois `nextjs-developer`)

Ciclos: 0/2. Conferido pelo orquestrador antes do despacho: `util.competencia_janela`
**não existe** — a janela 21→20 vive só em `dp/ciclo.py:158`; e nada no front
chama `fn_revisar_justificativa` (o RH não tem tela para aprovar).

**Decisões do dono, 29/09/2026 (paradas cumpridas):**
- **Janela da fila: 21→20** (responde a pergunta aberta 7.2 para a fila). Nasce
  `util.competencia_janela` em SQL, com teste de paridade contra `ciclo.py`.
- **Exposição:** `public.fn_fila_aprovacao`, `security invoker`, chamada só pelo
  backend como o usuário (padrão de `fn_pending_justification`).
- **Quem vê:** só `hr` e `owner`; os demais papéis recebem 403 no backend.

Ordem: backend (migration, rotas de fila e de revisão) → frontend (tela do RH).

**Backend entregue, 29/09 (`fastapi-developer`):** migration
`20260929233425_alcada_approval_queue.sql` (`util.competencia_janela` immutable,
com `execute` a `authenticated`/`service_role` porque a fila é invoker;
`public.fn_fila_aprovacao` invoker, vazia para quem não é `hr`/`owner` no
tenant da linha); `routers/alcada.py` com `GET /alcada/fila` (403 `not_hr`) e
`POST /alcada/justificativas/{id}/revisao` (`extra="forbid"`; 403
`not_hr`/`own_justification`/`owner_only`, 404 `justification_not_found`, 409
`already_reviewed`/`source_is_mirror`/`not_pending`/`no_open_period`, 422
`rejection_needs_reason`); `scripts/80_teste_janela_competencia.py` (paridade
48/48 com `ciclo.py`); 98 +39 asserções (só acréscimos); pytest 40 novos. 18
mutações de banco e 8 de backend, todas mortas. **Conferido pelo orquestrador
na árvore real** depois de apagar a exceção de docs vencida
(`util.competencia_janela`): `=== SUÍTE COMPLETA OK`, pytest 1630, ruff limpo.
Pendências declaradas: desvio revogado com justificativa pendente segue na
fila (dívida da P1.2); `de > ate` devolve vazio sem 422.

**Decisão do dono, 29/09 (parada: coluna nova em `public`):** a fila devolve
`can_review boolean` e `blocked_reason` (`own_justification`/`owner_only`) —
o RH vê o item bloqueado e o motivo. Devolvido ao desenvolvedor.

**Entregue, 29/09:** as duas colunas saem de um `cross join lateral` com os
passos 3 e 4 da RPC, na mesma ordem; `ApprovalQueueRow.blocked_reason` é
`Literal` (código desconhecido quebra a validação). 98 +7 asserções (só
acréscimos, numstat `792 0`), com `pg_temp.paridade` chamando a RPC de verdade
em cada linha da fila e desfazendo — fila bloqueada ⇔ RPC recusa com o mesmo
código. 7 mutações mortas pela paridade sozinha. Suíte verde, pytest 1632,
ruff limpo, segundo o desenvolvedor. Limites declarados: as 26 mutações
anteriores não foram refeitas sobre a assinatura nova; o pytest da fila usa
stub.

**Frontend entregue, 29/09 (`nextjs-developer`):** rota
`/dashboard/justificativas/aprovacao` (`notFound()` fora de `hr`/`owner`; 403
da API → "Sem acesso"; API fora → "não pôde ser lida", nunca fila vazia);
filtros na query string (`ano`, `mes`, `un`, `col`, `de`, `ate`), competência
padrão pela regra 21→20 copiada no front só para o padrão e a exibição; item
com `can_review=false` sem botões e com o motivo; salvaguarda de dois cliques;
reprovar exige motivo (Zod + 422 no campo); os nove códigos com texto pt-BR;
link na navegação só para `owner`/`hr` (`personnel` fora, testado). 9 mutações
em cópia, todas vermelhas. Premissas: filtro de colaborador lista só quem está
na fila; aprovar envia observação opcional como `motivo`; sem paginação.

**Conferido pelo orquestrador na árvore real, 29/09:** `=== SUÍTE COMPLETA OK`,
pytest 1632, ruff limpo, Vitest 1278/1278, prettier e tsc limpos. Revisão da
P1.3 inteira despachada a `code-reviewer` e `guardiao-da-alcada`.

**`guardiao-da-alcada`, 29/09 — REPROVADO (um item).** 7 estático: a regra
21→20 está copiada como constante em `frontend/src/lib/alcada/url.ts`
(competência padrão, frase da janela e `min`/`max` das datas em
`approval-filters.tsx`), e o `url.test.ts` só a testa contra ela mesma — se o
banco mudar, a tela declara uma janela e filtra outra, sem nada vermelho.
**Leitura do orquestrador:** a decisão do dono já é "a janela vive em
`util.competencia_janela`"; a cópia foi premissa do desenvolvedor, então o
conserto (a janela vir do backend) não é decisão nova. Passam: suíte completa
em banco próprio; 1–6; 7 funcional (bordas 20/21, supervisor vazio por todos os
filtros nas 12 competências de 2026, owner B só B, segunda camada sem a checagem
de papel ainda prende à unidade, paridade nos dois papéis, `anon` sem EXECUTE);
121 = 121 policies; ACL de função só com os dois grants esperados; 98 `792 0`,
99 intacto. 2(b)/(c) barrado — dado por medido, como na P1.2 (a sprint não toca
motor nem produção).

**`code-reviewer`, 29/09 — APROVADO.** Suíte em banco próprio, pytest 1632,
Vitest 1278, lint limpos. Mutações refeitas por ele sobre a assinatura nova,
todas mortas: janela (4 + constante), filtros (7), papel (6), invoker→definer,
paridade dos dois lados (inclusive mutando a RPC), `anon`, 12 de backend e 12
de front. BAIXOS: fila em `public` alcançável pelo PostgREST por RH logado
(mesmo dado; padrão escolhido pelo dono); mutação "papel em qualquer tenant"
sobrevive — nenhuma fixture tem usuário em dois tenants; data impossível na URL
cai em "API não respondeu"; seletor de colaborador limitado ao recorte; troca
do tipo de retorno exige que nenhum banco compartilhado tenha a versão anterior.

**Ciclo 1/2 despachado em 30/09** com o item 7 do guardião (a janela e a
competência corrente passam a vir do backend; a cópia do front sai), a asserção
de usuário em dois tenants e a data impossível na URL.

**Backend do ciclo 1, 30/09:** `GET /alcada/fila` devolve `{ano, mes,
period_start, period_end, rows}`; `ano`/`mes` opcionais e juntos (só um → 422
antes de abrir transação); sem os dois, `tenant_clock(tenant).today` →
`util.competencia_de(date)` (helper novo na mesma migration, sem 20/21 no
corpo: pergunta a `competencia_janela` qual das duas candidatas contém a data).
O 403 continua antes do relógio. `relogio.py` só mudou o tipo do parâmetro
(`SystemContext` → `Bound`). 80 estendido a 1461 dias; 98 +6 asserções do
usuário `hr` em A e `unit_supervisor` em B (numstat `835 0`) — a mutação "papel
em qualquer tenant" agora morre. 23 mutações de banco e 4 de backend, todas
mortas. Segundo o desenvolvedor: suíte verde, pytest 1636, ruff limpo.

**Frontend do ciclo 1, 30/09:** o agente parou sem relatório (a sessão acabou);
o orquestrador conferiu o que ficou na árvore: `competenceOf`/`competenceWindow`
fora do `url.ts`; a página e os filtros leem `period_start`/`period_end`/`rows`
da resposta; `competence-rule.test.ts` procura regra 20/21 em `lib/alcada` e
`components/alcada`; `isCalendarDay` descarta `2026-02-31`; 422 → "Recorte
inválido". **Sem relatório de mutações do front** — fica para os revisores.

**Conferido pelo orquestrador na árvore real, 30/09:** `=== SUÍTE COMPLETA OK`,
pytest 1636, ruff limpo, Vitest 1293/1293 (a primeira rodada teve 1 falha por
timeout em `canais/labels.test.ts`, fora da alçada, que passa 11/11 sozinho e na
rodada seguinte), prettier e tsc limpos. Re-revisão despachada.

**`guardiao-da-alcada`, ciclo 1 — APROVADO.** A sessão caiu no meio; ele refez
tudo (Docker tinha fechado). Suíte verde em banco próprio; 1, 2(a), 3–6 PASSA;
**7 PASSA, funcional e estática**: bordas 20/21 na fila e em `competencia_de`,
supervisor vazio; nenhum 20/21 fora dos testes nos três diretórios do front,
nem no corpo da fila e de `competencia_de`; mutação `CUTOFF_DAY = 20` no
`url.ts` reprova no `competence-rule.test.ts`. Policies idênticas ao gate
anterior (121), grants de tabela idênticos, única ACL nova `execute` de
`util.competencia_de` sem `anon`. 98 `835 0`, 99 intacto. 2(b)/(c) barrado,
dado por medido.

**`code-reviewer`, ciclo 1 — APROVADO.** Refeito do zero (a máquina reiniciou).
Suíte em banco próprio (a primeira rodada caiu em `tuple concurrently updated`
na migration 01, corrida com o guardião; a segunda passou), pytest 1636, Vitest
1293, lint limpo. r6 agora morre; mutações de `competencia_de`, das rotas (par
`ano`/`mes`, 403 antes do relógio, `date.today()`) e do front (regra 20/21
reintroduzida de três formas, `min`/`max`/frase, data impossível, 422, links)
morrem. MÉDIOS: (1) o `page.test.tsx` sempre mocka `rows: []` — descartar as
linhas da resposta sobrevive; (2) `tenant_clock` abre um `tenant_scope` (2ª
conexão do pool de 10) com o `user_scope` aberto — 10 leituras simultâneas sem
`ano`/`mes` esgotam o pool; a docstring do router ficou falsa. BAIXOS: r6b
("owner em qualquer tenant" no `blocked_reason`, só exibição); B4 (nenhum teste
com `de` confere a janela da resposta); `years()` oferece 2101; `ISO_DAY`
duplicado.

**Fechamento da P1.3, 30/09:** ✅ aprovada (ciclo 1/2). Os dois MÉDIOS e o B4
entram como reforço depois do gate (precedente da P0.1), conferidos pelo
orquestrador. Não commitada, nada em produção.

**Reforço do front, 30/09 (`nextjs-developer`):** `page.test.tsx` ganhou caso
com linha (a linha aparece na fila e no seletor de colaborador) — as mutações
`rows={[]}` na fila e nos filtros morrem; `ISO_DAY` duplicado saiu (usa
`isCalendarDay`); `years()` limitado a `YEAR_MIN`/`YEAR_MAX`. O relatório do
ciclo 1 do front chegou junto: 9 mutações, todas mortas. Vitest 1295, prettier
e tsc limpos, segundo o desenvolvedor.

**Reforço do backend, 30/09 (`fastapi-developer`):** `relogio.py` ganhou
`user_clock(scope: UserScope)` (mesmo `_TIMEZONE_SQL`, filtrado pelo tenant do
token, na transação do usuário; a escolha do fuso foi para um `_clock(row)`
comum), e `tenant_clock` voltou a `SystemContext` — o motor não muda. A rota lê
o relógio depois da checagem de papel, na mesma conexão; premissa escrita: só
vale para quem vê todas as unidades, e quem chega ali é `hr`/`owner`. Teste com
`tenant_scope` sabotado (abrir um reprova) e relógio congelado em 23:30 de 20/12
em São Paulo (= 21/12 UTC) → `today` 20/12. B4: o teste de filtros usa
`de = 28/12` e afirma a janela do banco. 5 mutações mortas (a do pool morre pela
asserção de conexão, não por `NameError`). pytest 1636, ruff limpo.

## P1.4 — Lançamento no Secullum · ✅ aprovada 04/10 · `fastapi-developer` + `nextjs-developer`

Ciclos: 0/2. Base: commits `790715e` e `dab283a` (P0–P1.3 e P1.2b), sem push —
as cinco migrations precisam entrar em produção antes, e esta sessão não
alcança produção.

**Decisões do dono, 01/10/2026 (paradas cumpridas: RPC nova em `public` e
contrato de API):**
- **Marcar:** `public.fn_marcar_lancado(review_id)`, `security definer`, no
  padrão da `fn_revisar_justificativa`: só `hr`/`owner`, só revisão
  `approved`, grava `posted_to_source_at` e `posted_by` uma única vez; a tela
  chama pelo FastAPI.
- **Desfazer:** não existe — é definitivo; engano vira correção por SQL de
  operador.

**Backend entregue em parte, 01/10 (`fastapi-developer`):** migration
`20261001112917_alcada_mark_posted.sql` — `public.fn_marcar_lancado` definer,
recusas `not_hr` → `review_not_found` → (lock) → `not_approved` →
`already_posted`, marca uma vez só, sem policy nem grant de tabela;
`POST /alcada/revisoes/{id}/lancamento` com corpo `{}` obrigatório
(`extra="forbid"`; o corpo opcional quebrava `test_contrato_corpo.py`), 403/404/
409/409. 98 +39 (só acréscimos), `scripts/78_teste_lancamento_concorrente.py`
novo; 8 mutações de SQL e 7 de Python mortas. Suíte verde, pytest 1659, ruff
limpo, segundo o desenvolvedor. Não aplicou `own_justification` nem
`owner_only` à marca (lançar não decide).

**Parada — a leitura "o que falta lançar" não foi feita:** pela competência da
revisão (§4.2), o RH não lê `app.payroll_period` (`payroll_period_read` exige o
domínio `compensation`, que `hr` não tem) — a lista viria vazia em silêncio; e a
fila recorta pelo fato enquanto a revisão cai na competência não fechada mais
antiga, então a mesma aprovação apareceria em competências diferentes. Levado
ao dono, com a regra do autor na marca.

**Decisões do dono, 04/10/2026:**
- **A lista se organiza pela competência do FATO** (janela 21→20 de
  `reference_date`, a mesma da fila) — diverge do §4.2 de propósito: alinha as
  duas telas e o Secullum, e não exige objeto novo nem policy.
- **O autor pode marcar como lançada** a própria justificativa já aprovada por
  outro: lançar não decide.
Devolvido ao desenvolvedor para a GET.

**GET entregue, 04/10:** `GET /alcada/lancamento` (mesmos filtros e o mesmo par
`ano`/`mes` da fila; 403 `not_hr` antes do relógio; `{ano, mes, period_start,
period_end, rows}`, todas as `approved`, pendentes primeiro, `posted_*` nulos =
pendente). Consulta no FastAPI sob `user_scope`, com o papel repetido na
consulta; nada novo em `public`; `_competencia` compartilhado com a fila. Os
nomes de quem aprovou e de quem lançou NÃO vêm (`auth.users` não é legível por
`authenticated`) — só os uuids. `scripts/77_teste_lista_lancamento.py` novo
(importa o SQL do router): separação, competência do fato (revisão gravada em
09, fato em 10 → aparece em 10), filtros, supervisor zero linha mesmo sem o
pré-teste, tenants. 8 mutações mortas (3 só pelo 77). Cabeçalho da migration
registra as decisões de 04/10; SQL inalterado.

**Conferido pelo orquestrador na árvore real, 04/10:** `=== SUÍTE COMPLETA OK`,
pytest 1678, ruff limpo. Tela despachada ao `nextjs-developer`.

**Tela entregue, 04/10 (`nextjs-developer`):** `/dashboard/justificativas/lancamento`
(`notFound()` fora de `hr`/`owner`; link no menu sob o mesmo `showApprovals`);
"A lançar no Secullum" e "Já lançadas" separadas só pela marca, contagem de
pendentes em destaque; dois cliques com "a marca é definitiva"; POST com `{}`;
o item muda de seção após o 200; `already_posted`/`review_not_found` recarregam;
nenhum uuid na tela ("por você" via `/me`); filtros na query string, janela da
resposta, `competence-rule` estendido aos arquivos novos; 403/422/indisponível
nunca viram "nada a lançar". `alcadaHref` e o leitor de API compartilhados com
a aprovação, sem mudar o comportamento dela. 14 mutações em cópia, todas mortas.

**Conferido pelo orquestrador na árvore real, 04/10:** pytest 1678, Vitest
1342/1342, prettier e tsc limpos (a suíte de banco já tinha fechado OK depois da
GET; a tela não toca banco). Revisão despachada.

**`guardiao-da-alcada`, 04/10 — APROVADO.** Suíte verde em banco próprio.
Catálogo sem × com a migration: a única diferença é `public.fn_marcar_lancado`
(definer, `execute` a `authenticated`/`service_role`, sem `anon`/PUBLIC);
`review_read` segue a única policy; nenhum UPDATE de `authenticated` na tabela.
Marca como usuário: `not_hr` (supervisor, DP), `review_not_found` (outro
tenant), `not_approved`, `already_posted` com uma marca só; UPDATE direto →
`permission denied`. Lista: consulta crua como supervisor devolve 0; 4 mutações
mortas no 77; borda 20/21 conferida chamando `posting_list`. 1, 2(a), 3–7
PASSA; 98 só acréscimos, 99 intacto. 2(b)/(c) barrado, dado por medido.

**`code-reviewer`, 04/10 — APROVADO.** Suíte em banco próprio, pytest 1678,
Vitest 1342, lint limpos. Mutações refeitas e mortas: sem `for update` (pelo 78),
sem `already_posted`, lock antes do tenant, papel em qualquer tenant; na GET,
sem o papel, janela pela revisão, sem `r.tenant_id`, sem `approved`; 7 no front
(inclusive o refator compartilhado não muda a aprovação). Outro tenant não vaza
estado. MÉDIOS (só dado no 77): bordas 20/21 da janela do fato não testadas
(borda exclusiva sobrevive); nenhum caso com desvio, então `coalesce(d.unit_id,
e.unit_id)` invertido sobrevive. BAIXOS: guardas de casos impossíveis no
router; `posted_by` da resposta vem do token, não do banco; a RPC recorta pelo
tenant da linha (como a de revisão); a mensagem de `already_posted` dizia "por
outra pessoa", o que é falso na mesma pessoa em outra aba — **corrigida pelo
orquestrador** ("já estava marcada"; os testes da alçada no front passam
118/118); sem `loading.tsx` (padrão anterior).

**Fechamento da P1.4, 04/10:** ✅ aprovada (sem ciclo de correção). Os dois
MÉDIOS entram como reforço de dado no 77 antes do commit.

**Reforço do 77, 04/10:** bordas da janela (20/09 → 2026/09, 21/09 → 2026/10,
21/08 → 2026/09, 20/08 → 2026/08) e um desvio na unidade Dois de colaborador hoje
na unidade Um; a borda exclusiva (6 falhas) e o `coalesce` invertido agora morrem.
Só o 77 mudou; 18 verificações.

**Conferido pelo orquestrador na árvore real, 04/10:** `=== SUÍTE COMPLETA OK`,
pytest 1678, ruff limpo, Vitest 1342/1342, prettier e tsc limpos. Commitada.

---

## Etapa da alçada — ✅ fechada no código em 04/10. Nada em produção.

Commits `790715e`, `dab283a` e o da P1.4, sem push. Seis migrations precisam
entrar em produção ANTES do push, nesta ordem:
`20260928235913_holiday_calendar`, `20260929010543_alcada_justification_pending`,
`20260929114738_alcada_justification_review`, `20260929233425_alcada_approval_queue`,
`20260930225115_alcada_revoke_writes`, `20261001112917_alcada_mark_posted`.
Depois o push do backend (os dois crons e a API reconstroem), depois
`vercel promote`. Com a de feriado, o `operax-motor-retro` reprocessa o 07/09.

**Migrations aplicadas em produção, 04/10, com autorização do dono:** antes, o
ledger de `nklobmlxyidqxarzisph` foi comparado com o repositório — faltavam
exatamente as seis, nada mais. Uma por chamada da Management API, cada uma
transacional e com o registro em `supabase_migrations.schema_migrations`
(`version`, `name`) na mesma transação; todas voltaram sem erro e com o `do $$`
de cada uma satisfeito. Conferido no catálogo de produção: ledger 78 → 84;
`app.holiday`, `app.justification_review`, `fn_revisar_justificativa`,
`fn_fila_aprovacao`, `fn_marcar_lancado` e `util.competencia_de` existem;
`authenticated` sem INSERT em `justification` e sem UPDATE em `tenant_member`;
`anon` sem EXECUTE na fila; 104 policies em `app`; zero tabelas em `public`.

**Push barrado pelo classificador** (publicação). O código em produção segue o
anterior sobre o schema novo, o que é compatível: a rota antiga grava pelo
`tenant_scope` como `postgres` (o default `pending` e a trava do espelho não a
afetam, porque ela passa `status` explícito com `source='operax'`), e o motor
antigo não lê nada que mudou. Falta o dono fazer o push e o `vercel promote`.

**Push feito em 04/10 (autorizado pelo dono):** `f0912e0..aecc0e7`, levando junto
`62aa8e7`, `f8a865f` e `9dfb579`, que estavam sem push. Os seis serviços do
Railway (`operax-api`, `operax-motor`, `operax-motor-retro`, `operax-vigia` e
dois ids que a memória não registrava: `d6c5320e…`, `f7a91382…`) terminaram em
SUCCESS. `GET /health` = ok. O `operax-motor` das 19:30 UTC rodou no código novo
sem erro (detecção aberta e fechada, "nenhum feriado a reprocessar").

**Carga dos feriados nacionais, 04/10 (autorizada pelo dono):** `app.holiday`
estava com zero linhas — a migration cria a tabela, a carga é passo à parte.
Rodada pelo `sb_sql.sh` com o SQL gerado das funções do repositório
(`national_holidays`, `_LOAD_SQL`, `_LOAD_AUDIT_SQL`), tenant FastPark, 2026 e
2027: 20 inseridos, 1 linha de auditoria. O `operax-motor-retro` das 05:20 deve
reprocessar o 07/09 (escrito há menos de 48 h); conferir no dia seguinte.
Falta o `vercel promote` do frontend.


**Acesso do Thiago, 04/10 (autorizado pelo dono; fora da etapa, registrado por
ter sido escrita em produção):** usuário `thiago@kastropark.com.br` criado pela
API de admin do Supabase Auth (chave de serviço de `backend/.env.production`,
lida no script sem ser impressa), já confirmado; vínculo `owner` ativo no tenant
FastPark (`app.tenant_member`), num tenant só. Login com senha testado contra o
Auth de produção: 200 com token.

**`vercel promote`, 04/10 (autorizado pelo dono):** preview do push (criado 19:27
UTC, mesmo minuto) promovido; a build de produção `operaxfonted-bcnyd0kos` ficou
Ready. Em `app.fastparks.com.br`, `/`, `/dashboard/justificativas/aprovacao` e
`/dashboard/justificativas/lancamento` respondem 307 para `/login?next=…` sem
sessão — as rotas existem e passam pelo login. **A etapa da alçada está em
produção ponta a ponta.** Conferir em 05/10: o `operax-motor-retro` das 05:20
corrigindo o 07/09.
