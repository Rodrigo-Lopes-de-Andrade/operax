<!-- verificar-docs: inexistentes-de-proposito public.fn_dp_panel app.work_schedule_day app.messaging_identity -->
<!-- `app.work_schedule_day` continua aqui porque o Quadro REPORTA que ela não
     existe — e agora a SPEC diz o mesmo, então a contradição entre os dois
     documentos acabou. `app.schedule_rotation_map` SAIU desta lista: ela existe
     (migration 25), e declarar exceção para objeto existente é mentira que o
     verificador não pega, porque ele só suprime e nunca reclama de sobra.
     ⚠️ `app.benefit_type` e `app.work_post` SAÍRAM em 06/09 pelo mesmo motivo:
     `dp_work_post` e `dp_benefit_catalog` as criaram, e a suíte confirmou. Uma
     exceção que sobrevive ao objeto que ela desculpava é a forma silenciosa
     deste verificador ficar cego — ele suprime e nunca reclama de sobra.
     ⚠️ `public.fn_dp_alerts` SAIU em 07/09 pelo mesmo motivo: o S4 a criou.
     ENTRARAM `public.vw_unit_compliance` e `app.unit_compliance_report`, que
     descem para o S5 — o S4 as cita para dizer que NÃO as constrói, e a tabela
     é do sprint seguinte. `public.fn_dp_panel` fica: ela deixou de ser planejada
     em 06/09 (o painel vai pelo Caminho 2) e o documento a nomeia justamente
     para registrar que ela não existe. -->

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
- Semente de `app.benefit_type` com **8 tipos** e o `composes_base` da tabela da
  SPEC §1d — é a definição do KPI. Transcreva; não derive.
- ⛔ **São OITO, e o nono é nomeado:** `seniority_bonus` **não entra**. A medição
  da §1d-bis não teve resposta empírica (`app.payroll_entry` com zero linhas), e o
  owner decidiu em 04/09, reconfirmando em 05/09 no despacho: o triênio fica fora
  até haver folha importada. Somá-lo enquanto talvez já esteja no salário conta
  duas vezes e corrompe o KPI sem sintoma.
- ⚠️ **As colunas do triênio ficam** — `benefit_type.calculation` e
  `employee_benefit.rate`/`quantity`. Saiu o tipo da semente, não o mecanismo.
- `app.employee_position` ganha `work_post_id` e `level`.
- Backend: `/dp/postos` e `/dp/beneficios/catalogo` + reajuste por vigência.

**Gate:** o teste da folha base passa — salário + ajuda de custo + cargo de
confiança + periculosidade entram, VR fica fora — sobre fixture sintética. Um
reajuste de tarifa cria vigência nova e **não** altera a anterior.

⚠️ **O caso do triênio continua no gate, e vem da fixture, não da semente.** O
teste cria um tipo `salary_rate` sintético e prova que um aumento de salário
**muda o valor dele na mesma leitura** — é taxa, não montante. O mecanismo é
testado sem que o tipo exista em produção, que é exatamente o desenho.
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

🔴 **S4 não tem para quem mandar esses dois templates, e isso não é escopo dele.**
Registrado em 05/09/2026, vindo da etapa de canais, e **medido aqui antes de ser
escrito**: `app.contact` tem `name · whatsapp · email · type` e
**nenhum elo com `app.employee`** — `type` só aceita `person`, `whatsapp_group` e
`email_list`, e `app.unit_responsible` liga contato a unidade, não a colaborador.

Os dois templates são endereçados ao **colaborador** (aniversário dele, CNH
dele). A etapa de canais resolve o destino de **Telegram** (`app.messaging_identity`,
com titular `contact_id` XOR `employee_id`); a rota de **WhatsApp para
colaborador continua sem modelo de destinatário**.

⛔ **Isto precisava de decisão antes de S4 começar**, e as opções não eram
equivalentes: estender `app.contact` com elo opcional para colaborador, ou usar o
`app.messaging_identity` da etapa de canais como modelo único de endereço. A
segunda acopla S4 ao C3. Sem escolher, S4 entregaria dois templates que não têm
destinatário — e o sintoma é uma fila que nunca sai.

✅ **Decidido pelo dono em 06/09/2026: os dois templates SAEM do S4.** Ele entrega
o painel, os 9 KPIs e os 8 cartões de alerta — que é o valor dele —, e
`birthday_greeting` e `cnh_renewal_request` descem para quando existir modelo de
endereço. O próprio plano já dizia que o destino *"não é escopo dele"*.

⚠️ **A medição que fechou a decisão foi refeita em 06/09 e é mais dura que o
texto acima:** `app.contact` tem `name · whatsapp · email · type` e **nenhum
`employee_id`** (migration 04, linhas 178-187); e `app.messaging_identity` **não
existe em migration nenhuma** — só em `SPEC-CANAIS.md` —, onde o check é
`channel in ('telegram')`. Ou seja: **não há modelo de destinatário de WhatsApp
para colaborador em lugar nenhum do produto**, nem no DP nem na etapa de canais.
A opção "usar o `messaging_identity`" não resolveria sem alargar o canal e
construir a tabela antes.

📌 **Consequência para o escopo do S4:** saem os dois templates e o
`util.validate_alert_template` que os cobriria. Ficam `dp_movement_period`,
`dp_leave_extension`, `dp_cadastral_fields` e `dp_panel_views`. **A parada de
"coluna nova em view pública" continua de pé** — `public.fn_dp_panel` e
`public.fn_dp_alerts` são superfície de `public`.

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
| S1 — Fundação | ✅ **aprovada** (06/09) — **backend e banco; a metade de frontend não foi despachada** | `dp_work_post`, `dp_benefit_catalog` | guardião ✅ · revisor ✅ | 2 |
| S2 — Domínio `banking` | ✅ **aprovada** (05/09) | `dp_banking_domain`, `dp_banking_account` | guardião ✅ · revisor ✅ | 1 |
| S3 — Ciclo mensal | ✅ **aprovada** (06/09) — **backend e banco; frontend não despachado; reconciliação com o legado ABERTA** | `dp_benefit_cycle`, `dp_leave_category`, `dp_absence_map` | guardião ✅ · revisor ✅ | 2 |
| S4 — Painel e alertas | ✅ **aprovada** (07/09) — **backend e banco; frontend não despachado; reconciliação dos 9 KPIs ABERTA** | `dp_movement_period`, `dp_leave_extension`, `dp_cadastral_fields`, `dp_panel_views` | guardião ✅ · revisor ✅ | 2 |
| S5 — Laudos e rubricas | ✅ **aprovada** — backend e banco (08/09), **frontend (12/09)** | `dp_unit_compliance`, `dp_payroll_code_map` | guardião ✅ · revisor ✅ (backend) · revisor ✅ (frontend) | 2 + 3 (frontend) |

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

## Despacho de 05/09/2026 — as cinco paradas, conferidas antes

| # | Condição | Conferida como |
|---|---|---|
| 1 | os quatro documentos | ✅ os quatro estão versionados desde `bd85089` |
| 2 · FORCE | ✅ fechada por medição e decisão — §2a-bis e `DECISAO-FRONTEIRA-CAMINHO-2.md` |
| 2 · Captura | ✅ **conferida no código, não na tabela**: `capturar_producao.py` delega a `scripts/introspeccao_nuvem.py`, que captura `relrowsecurity`, `relforcerowsecurity`, `pg_policy`, ACLs de tabela, schema, função e `pg_default_acl`. Ela **não** é cega às flags de segurança |
| 3 | §1d-bis | ✅ decidida pelo dono em 04/09 — e é ela que retém S1, ver abaixo |
| 4 | arquivos e critérios | ✅ preenchidos |
| 5 | decisão fechada | ✅ nenhuma sprint pede |
| — | elenco contra `/agents` | ✅ `fastapi-developer`, `nextjs-developer`, `code-reviewer`, `guardiao-de-superficie` existem |

**Despachada: S2**, para `fastapi-developer`. Slot `dp_banking_domain` +
`dp_banking_account`, arquivos separados.

**S1 não saiu na mesma leva, por dois motivos — e o segundo revoga a
paralelismo do plano nesta máquina.**

**1. O ⛔ da semente, resolvido.** A SPEC §1d listava **nove** tipos com
`seniority_bonus` entre eles, contra a decisão do dono de 04/09 que o tira. A
regra do despachante é explícita — *"transcreva; não derive; parecendo errada,
pare e pergunte"* — então subiu. ✅ **Respondido em 05/09: são oito.** As colunas
do triênio (`calculation`, `rate`, `quantity`) **ficam**; saiu o tipo da semente,
não o mecanismo. SPEC §1d e o corpo de S1 corrigidos, e o gate agora exercita
`salary_rate` por fixture sintética.

**2. ⛔ A suíte de banco é recurso compartilhado e não reentrante.**
`scripts/testar_migrations.sh` começa com
`drop database if exists operax_test; create database operax_test`, contra o
**mesmo** container local. Dois agentes rodando o portão ao mesmo tempo derrubam
o banco um do outro no meio da corrida — e o sintoma é falha aleatória que parece
defeito de código.

O plano previu colisão de **slot de migration** e resolveu com um arquivo por
slot. Não previu colisão de **fonte** (`routers/dp.py` e `models.py`, que S1 e S2
criariam as duas) nem de **portão**. A de fonte se resolveria com worktree; a de
portão não se resolve com worktree nenhum, porque o banco é um só.

📌 **Consequência declarada: nesta máquina, S1 e S2 são sequenciais**, e o
"paralelismo real" do despachante vale para agentes com banco próprio. S1 é
despachada quando S2 reportar. Não é reordenação do plano — a ordem
S1‖S2 → S3 → S4 continua de pé; o que mudou é que a onda 1 executa em série.

⚠️ **Ajuste de `Arquivos` no despacho, declarado:** S2 recebeu também
`backend/server/models.py`, `backend/server/routers/__init__.py` e
`backend/server/main.py` — sem os três a rota nasce sem schema e sem registro. É
seguro porque S1 não está correndo em paralelo; com as duas juntas,
`routers/dp.py` e `models.py` seriam colisão de arquivo, não de slot de
migration. **O plano não previa colisão de fonte, só de migration.**

## 🔴 S2, ciclo 1 — a SPEC §1b afirma algo falso, e a Regra 0 se aplica

O revisor reprovou, e o motivo não é a sprint: **é a SPEC.** A §1b manda exigir
`can_see_domain` **e** `can_see_employee` — *"os dois eixos, como toda tabela
sensível do projeto"*. A sprint transcreveu isso, declarou a assimetria que
percebeu, e parou antes de aplicar. O processo funcionou.

**A segunda metade da frase é falsa, e se falsifica lendo o repositório:**

| Policy de escrita | Predicados |
|---|---|
| `pii_write` (04) | `can_see_domain('pii')` **+ `util.is_admin`** |
| `remuneracao_write` (04) | `can_see_domain('compensation')` **+ `util.is_admin`** |
| acordos (08) | `can_see_domain('compensation')` **+ `util.is_admin`** |
| `employee_photo_write` (36) | `can_see_domain('pii')` **+ `util.is_admin`** + `can_see_employee` |
| `employee_bank_account_write` (nova) | `can_see_domain('banking')` + `can_see_employee` — **sem `is_admin`** |

**Não existe uma única policy de escrita de domínio sensível neste repositório
sem `util.is_admin`.** Os dois eixos são o padrão de *leitura*; escrita sempre
carrega o terceiro. E a `36_employee_photo` — que a própria migration nova cita
como seu modelo — é justamente a que usa os três.

### O efeito é concreto, e medido

`util.is_admin` é `role in ('owner','hr','personnel')` — conferido no catálogo, não
na documentação. A semente concede `banking` a `owner`, `personnel` e
**`accounting`**. Então:

⛔ **`accounting` grava conta bancária.** Em toda outra tabela sensível ele lê e
não escreve.

⛔ **E a matriz é editável por `UPDATE`**, sem deploy (02, *"changes by UPDATE, not
migration"*). Conceder `banking` a `unit_supervisor` é uma linha de dado — e passa
a dar a ele **escrita** de conta bancária dos colaboradores da unidade dele.
Conceder `pii` ou `compensation` ao mesmo supervisor não dá escrita de nada.

Conta bancária é o campo que **redireciona pagamento**. É a operação de fraude
mais barata do produto, e ela ficou disponível para o papel que o resto do modelo
mantém em leitura.

📌 **Regra 0:** a premissa escrita na SPEC caiu ao ser conferida. Autorização
revogada automaticamente — nada se aplica antes de o dono decidir entre acrescentar
o terceiro eixo ou registrar por escrito que `accounting` escreve conta.

## 🔴🔴 Escrita mais frouxa que leitura, em DUAS tabelas já aplicadas

**Não é da etapa DP.** Achado de passagem pelo revisor na S2, e **conferido no
catálogo por quem orquestra** antes de escalar — porque a primeira versão do
achado estava errada e a segunda não.

| Tabela | Policy de **leitura** | Policy de **escrita** |
|---|---|---|
| `app.disciplinary_event` (migration **32**, aplicada) | `can_see_domain('disciplinary')` **+ `can_see_employee`** | **só `can_see_domain`** |
| `app.occupational_exam` (migration **08**, aplicada) | `can_see_domain('health')` **+ `can_see_employee`** | **só `can_see_domain`** |

Nos dois casos o `using` e o `with check` são idênticos entre si — o defeito não é
assimetria interna da policy, é a **escrita pedir menos que a leitura da própria
tabela**.

⛔ **Impacto:** quem tem o domínio pode **inserir** um registro contra qualquer
colaborador do tenant, **inclusive gente que não pode nem ler** — e um `update`
sem `where` alcança todas as linhas do tenant. É adulteração e fabricação dentro
do tenant, não vazamento de leitura. Numa tabela cujo conteúdo é advertência com
texto livre sobre uma pessoa, e noutra que guarda aptidão ocupacional.

⚠️ **Dois agravantes:**

1. **`app.disciplinary_event` tem `grant select, insert, update to authenticated`**
   (32, linha 73) — ou seja, é alcançável pelo **Caminho 1**. O que separa o
   navegador dela hoje é a configuração de *exposed schemas*, que é exatamente a
   que já regrediu em produção em 27/08/2026.
2. A **32 copiou o padrão da 08**, então são duas tabelas e não um deslize
   isolado. Qualquer tabela sensível futura que copie qualquer uma das duas
   herda o buraco.

📌 **Correção exige migration nova** — as duas estão aplicadas, e migration
aplicada não se edita. **Fora do escopo de S2 e de toda a etapa DP**; entra como
item próprio, e é o de maior severidade aberto hoje.

## 🔴 A guarda do `99` é nominal, e a asserção que a torna estrutural já tem forma

Item próprio, **fora de S2**, medido duas vezes pelo guardião (05/09/2026).

Concedendo `select` a `authenticated` numa tabela de `app`, o
`scripts/99_verificacao_rls.sql` **sai com exit 0**. Quem pega são duas asserções
**escritas à mão para aquela tabela** — uma no bloco `do $$` da migration e uma no
`98`. Nenhuma das duas existe para a tabela que alguém criar amanhã.

A causa é localizável: o **check 4** do `99` faz exatamente o laço certo — grant a
`authenticated`, verbo a verbo — mas **só para `secullum`**. `app` não tem
equivalente.

📌 **A forma da correção, e o detalhe que decide se ela funciona:**

> Um **inventário default-deny** de grants de `app` para `authenticated` no `99`:
> o mesmo laço do check 4, trocando o schema, falhando em qualquer um dos quatro
> verbos para toda tabela de `app` que não esteja numa allowlist.
>
> ⛔ **E a allowlist tem de ser DERIVADA, não escrita:** "a tabela é base de alguma
> view de `public`", via `pg_depend`. É só isso que legitima o grant no Caminho 1.
> Lista à mão volta a ser nominal, e o próximo `employee_bank_account` entra nela
> por engano.

Isso fecha o buraco para **toda tabela futura** em vez de para a tabela que alguém
lembrou de nomear — e é a diferença entre a etapa DP criar dez tabelas protegidas
e criar dez tabelas que dependem de dez pessoas terem lembrado.

### ⚠️ E um buraco menor no mesmo gate

`!!! ensaio dos ciclos de sincronização NÃO RODOU` — falta `ENSAIO_DATABASE_URL`,
e **o script avisa e sai 0 assim mesmo**. Não toca `banking` e não bloqueou nada
hoje, mas um passo que não roda e não reprova é um passo que ninguém vai notar
faltando. Vale decidir se ele deve falhar alto ou sair do gate.

## O falso verde deixou de ser hipótese em 05/09/2026

O despachante manda perguntar, antes de aceitar critérios: *que implementação
errada passa em todos estes?* Na S2 a pergunta foi **respondida por execução**, e
o resultado justifica a regra melhor do que qualquer argumento.

O guardião mutou a semente para dar o domínio `banking` ao `hr` — exatamente o
erro que o gate existe para pegar. **A asserção literal do gate,
*"`hr` recebe `permission denied`"*, continuou VERDE.** Quem pegou foram as
asserções positivas.

O motivo é estrutural e vale para toda tabela sensível deste produto: a tabela
não concede nada a `authenticated`, então `select` é `permission denied` para
**todo mundo** — inclusive para quem tem o domínio. O negativo mede a ausência de
grant, não a policy. Sem o par positivo, o conjunto ficaria verde num banco onde
ninguém lê nada, que é a definição do defeito.

📌 **Consequência para as sprints seguintes:** todo gate desta etapa que disser
"papel X é barrado" precisa do "e o papel Y passa" ao lado, e o positivo tem de
ser avaliado **contra a policy real** (o `pg_temp.policy_says` do `98` lê a `qual`
de `pg_policies` na sessão do usuário), nunca contra uma cópia da regra no teste.

### 🔴 Uma guarda permanente tem buraco, e não é desta sprint

Medido pelo guardião: com `grant select` para `authenticated` de pé numa tabela
de `app`, **`scripts/99_verificacao_rls.sql` sai com exit 0**. Quem pegou foi o
`98`, e pegou porque **nomeia esta tabela**.

Ou seja: a proteção não é estrutural, é nominal. **A próxima tabela sensível de
`app` não herda a guarda** — ela precisa que alguém lembre de escrever a
asserção. Fora do escopo de S2; entra como item próprio, porque é o tipo de
buraco que só aparece quando já vazou.

## Despacho de 06/09/2026 — S1, e a metade que chegou sem despacho registrado

A onda 1 executa em série nesta máquina (§ acima). S2 reportou e foi aprovada em
`bd175d4`, então S1 saiu.

⚠️ **A metade de banco do S1 já estava no disco quando este despacho começou** —
`dp_work_post` e `dp_benefit_catalog`, escritas em 06/09 às 04:23 e 04:26, **não
versionadas**, com a sprint ainda marcada `⛔ retida`. É exatamente o estado que a
regra 3 do despachante existe para não deixar acontecer: *"sprint marcada
`pendente` com trabalho no disco é indistinguível de uma nunca iniciada"*. O
status foi corrigido para `em execução` antes deste despacho, e fica registrado
que a correção veio depois do trabalho, não antes.

**O que foi medido antes de construir em cima:** a suíte inteira
(`scripts/testar_migrations.sh`) rodou com as duas migrations no diretório e
fechou `SUÍTE COMPLETA OK` — as 40 aplicam em ordem, o isolamento passa, o
dicionário regenera e `verificar_docs.py` fica verde. **A metade de banco do S1
está verde**, e o slot está fechado: o agente de backend lê as duas e reporta em
vez de editar.

Conferência das paradas, refeita para este despacho:

| # | Condição | Estado em 06/09 |
|---|---|---|
| 1 | os quatro documentos | ✅ os quatro no repositório |
| 2 | FORCE · captura | ✅ fechadas em 05/09 — §2a-bis e `DECISAO-FRONTEIRA-CAMINHO-2.md` |
| 3 | §1d-bis · a semente | ✅ **a parada do S1 caiu**: são oito, e o bloco `do $$` da migration falha alto se `seniority_bonus` aparecer |
| 4 | arquivos e critérios | ✅ preenchidos, e o gate ganhou quatro asserções — abaixo |
| 5 | decisão fechada | ✅ nenhuma sprint pede |
| — | elenco contra `/agents` | ✅ os quatro agentes existem |

**Despachada: a metade de backend do S1**, para `fastapi-developer`. Arquivos:
`operax/dp/postos.py`, `operax/dp/beneficios.py`, `server/routers/dp.py`,
`server/models.py`, `tests/test_dp_beneficios.py`. Sem slot de migration — o do
S1 está fechado.

### A pergunta do falso verde, aplicada ao gate do S1

O plano dizia que os gates de S1, S3 e S5 são *"de igualdade contra o legado, que
são positivos por construção"*. ⚠️ **Isso é verdade do critério de reconciliação e
falso do gate escrito.** O gate do S1 é *"salário + ajuda de custo + cargo de
confiança + periculosidade entram, VR fica fora"* — e a implementação errada que
passa nele tem nome:

⛔ **Uma lista de códigos escrita no backend passa em todas essas asserções.** Ela
soma os três certos, exclui o VR, e fecha verde — enquanto destrói a única coisa
que `benefit_type.composes_base` existe para dar, que é o cliente mudar a
definição do KPI sem deploy. O gate mediria o resultado e não o mecanismo.

📌 **Quatro asserções acrescentadas antes do despacho** (acrescentar caso é o
processo funcionando; nenhuma asserção existente foi tocada):

1. **A fórmula lê o dado, não uma constante** — virar `composes_base` de um tipo
   dentro do teste e provar que **o total muda**. Total que não se mexe é a
   lista no backend, denunciada.
2. **A vigência fecha de verdade** — reajuste cria linha nova, a anterior mantém
   o valor que valeu, a leitura numa data antiga devolve o valor antigo, e o
   índice único parcial rejeita duas faixas abertas.
3. **O triênio por fixture sintética** — tipo `salary_rate` criado no teste (nunca
   na semente): aumento de salário muda o valor **na mesma leitura**. É taxa, não
   montante — e o mecanismo é provado sem que o tipo exista em produção, que é o
   desenho da §1d.
4. **Verba fora da vigência não conta**, e o catálogo de um tenant não devolve
   linha do outro.

## S1, backend — entregue em 06/09, e o gate provado por mutação

`fastapi-developer` reportou os cinco arquivos do escopo. **Portões conferidos
por quem orquestra, não aceitos do relato:** `uv run pytest -q` → **428 passed**;
`ruff check` + `ruff format --check` → limpos, 89 arquivos.

O que faz esta entrega valer mais que o verde: o agente **rodou três mutações
contra a própria implementação** e mostrou quais testes ficam vermelhos.

| Mutação aplicada de propósito | Testes que reprovaram |
|---|---|
| `composes_base` trocado por lista fixa de códigos | 4 |
| o fechamento da faixa anterior removido do reajuste | 6, incluindo a violação do índice parcial |
| o filtro de tenant virado tautologia (`is not null`) | 2 |

📌 **A terceira é a que mais importa, e confirma por medição o que
`DECISAO-FRONTEIRA-CAMINHO-2.md` §3 já dizia em prosa:** o `bind_tenant` **deixa a
tautologia passar** — ele é lint sintático, não fronteira. A resposta do agente
foi estrutural: o dublê de cursor exige `tenant_id = %(tenant_id)s` literal em
todo `select`/`update` que passa por `tenant_scope`, além de filtrar as linhas.
Sem essa asserção, o teste multi-tenant seria falso verde — a terceira vez nesta
etapa que a pergunta do falso verde paga.

⚠️ **E uma asserção que o gate não pediu:** um teste varre
`inspect.getsource(beneficios)` atrás dos oito códigos da semente. A asserção do
gate prova que o comportamento está certo na fixture; esta prova que o mecanismo
errado **não existe** nem num caminho que a fixture não exercite. É a diferença
entre medir o resultado e medir o desenho.

### As três coisas que o agente subiu em vez de decidir sozinho

**1. ⚠️ Não existe porta para criar a PRIMEIRA vigência de plano ou tarifa — e a
lacuna é do plano, não da entrega.** A SPEC §2 lista `GET /dp/beneficios/catalogo`
e `POST /dp/beneficios/reajuste`, e reajustar exige uma faixa aberta para
reajustar. Consequência: `app.benefit_plan` e `app.transport_fare` **nascem
vazias e ficam vazias**, e o catálogo é inutilizável até existir criação. O
agente não inventou a rota — reportou, que é a regra. **Sobe ao dono**: ou entram
`POST /dp/beneficios/planos` e `POST /dp/beneficios/tarifas` num sprint (S3 é o
candidato natural: é ele que consome tarifa), ou a carga inicial de plano e
tarifa entra por outro caminho. ⛔ **S3 depende disso**: o apurador de VT lê
tarifa, e tarifa nenhuma existe.

**2. 🔴→✅ A `dp_benefit_catalog` criava dois índices e não garantia nenhum.** O
bloco `do $$` conferia `tenant_id`, RLS, grants, as oito policies, `calculation`,
`rate`/`quantity` e a semente inteira — e **não** que
`benefit_plan_open_band_idx` e `transport_fare_open_band_idx` existem. A
`dp_work_post` ao lado garante o `unique` dela com o conjunto de colunas
comparado inteiro; o padrão estava no slot e a lacuna era só nesta.

O índice parcial é a **tradução estrutural** de "reajuste cria vigência nova",
que é o item 3 do gate. Garantia que não alcança o que a própria migration chama
de "o pior tipo" de divergência é o falso verde de novo, dentro da migration
desta vez. 📌 **Slot reaberto pelo orquestrador para exatamente este acréscimo** —
é *acrescentar* garantia, não enfraquecer, e nenhuma das duas migrations está
aplicada em lugar nenhum. Não consome ciclo: não é reprovação, é escopo reaberto.

**3. `test_dp_beneficios.py` carrega também os testes do Quadro de Postos.** Fica
como está: a lista `Arquivos` do S1 nomeia um arquivo de teste só, rota sem teste
é pior que nome largo, e a seção está declarada no docstring.

### Duas decisões de desenho que valem para as sprints seguintes

- **A regra de vigência é uma função Python, não um predicado SQL.** Escrita nos
  dois lugares ela divergiria, e a metade SQL é a que o pytest não alcança —
  **pytest não abre banco neste projeto**. Com a regra em Python, os seis itens
  do gate exercitam o código que roda em produção. O recorte de tenant continua
  sendo do banco. S3 herda isto: o apurador de ciclo é a mesma forma.
- **A leitura das cinco tabelas desta etapa não roda como o usuário, e é de
  propósito.** Elas não concedem nada a `authenticated` (as migrations fazem
  `revoke all`, e o `grant select on all tables` da 04 é pontual no tempo e não
  alcança tabela criada depois) — um `select` sob `user_scope` morreria com
  `permission denied` em vez de ser filtrado. Vai por `tenant_scope` com filtro
  explícito, e quem autoriza é a rota. O recorte por unidade dos postos vem de
  `app.unit`, que **é** legível pelo usuário e cuja policy chama
  `util.can_see_unit`: a regra continua morando na policy; aqui ela é consultada.

## S1, ciclo 1 — as duas revisões acharam a mesma coisa, sozinhas

`code-reviewer` **reprovou**; `guardiao-de-superficie` **escalou** em vez de
aprovar ou reprovar. Nenhuma reprovação automática disparou em nenhuma das duas.

⚠️ **O revisor recusou-se a contar o `SUÍTE COMPLETA OK` como evidência dele**,
porque não foi ele quem rodou — foi relato de terceiro. É o comportamento certo,
e vale registrar como padrão: quem revisa mede, ou declara que não mediu.

### O que as duas acharam em separado, e é o achado mais importante do ciclo

**As policies de leitura do catálogo eram mais frouxas que a rota.**
`benefit_type_read`, `benefit_plan_read` e `transport_fare_read` liam por
`util.has_tenant` — **sem domínio** — enquanto `GET /dp/beneficios/catalogo`
exige `compensation`. O guardião mediu que a policy dizia **sim** para o `hr`,
que a rota nega.

Não expunha nada hoje (sem grant a `authenticated`, e o Caminho 2 ignora RLS). O
que quebrava era a justificativa escrita no cabeçalho da própria migration — *"se
um PR futuro conceder `select` por engano, a policy é o que ainda está de pé"*.
Nesse dia ela não estaria.

✅ **Decisão do dono, 06/09: apertar a policy.** As três leituras passam a exigir
`util.can_see_domain(tenant_id, 'compensation')`. Escrita (`util.is_admin`) e
`work_post_read` (`util.can_see_unit`) ficam como estão.

### O guardião: seis itens verdes, e duas medições que mudam o que se sabe

**1. O argumento do grant se sustentou, e ele o testou em vez de aceitar.** Criou
tabela em `app` **sem `revoke` nenhum**: nasceu sem grant para `authenticated`.
📌 **`grant select on all tables in schema app` (migration 04) é pontual no tempo
e não alcança tabela criada depois** — então o `revoke all` das migrations do S1
é **defensivo, não load-bearing**. Vale para toda tabela futura de `app`.

**2. O falso verde da S2 se reproduz no S1, e os pares novos o cobrem.** Mutando
a semente para dar `compensation` ao `hr`, a asserção literal continuou verde e
**o par positivo pegou**. Ele levou o `98` de **52 para 96 asserções** — 230
adições, **zero remoções**, zero `skip`. O S1 tinha acrescentado zero.

Precisou generalizar o `pg_temp.policy_says`, que era preso a
`employee_bank_account`: `policy_says_on(tabela, policy, tenant, employee, unit,
qual|with_check)` lê de `pg_policies` na sessão do usuário — não é cópia da regra
no teste.

### O revisor: dois ALTO que a letra do gate não alcançava

**1. `read_base_payroll` lia estado atual dentro de uma função datada.** O filtro
era `status <> 'desligado'` — hoje, não `on`. Ler competência passada excluía quem
foi desligado depois dela: **o número do mês encolhe retroativamente, sem
sintoma**. É o gate do S3 que quebraria, onde "divergência de uma pessoa é falha
do gate" e a reconciliação roda sobre mês fechado.

**2. A regra de vigência do SALÁRIO não era exercitada — e o salário é o maior
termo da soma.** Medido: trocando o filtro de vigência por `list(bands)`, os 35
testes seguiam verdes. O teste que existia não pegava porque a faixa vigente era
também a de maior `effective_from`; um `max()` ingênuo passaria. O item 3 do gate
estava provado para tarifa e plano, **não** para o termo que domina o total.

**3. A asserção do dublê tinha o buraco que o despacho mandou procurar.**
`assert "tenant_id = %(tenant_id)s" in sql` pegava a tautologia **substitutiva**
— que foi a mutação do próprio implementador — e **não** a **disjuntiva**:
`where (tenant_id = %(tenant_id)s or true)` passava com 35 verdes. O SQL entregue
estava correto; o docstring é que prometia mais do que o teste entregava.

### O ciclo 1, fechado — 439 passed, tudo provado por mutação

Os oito itens entraram. O implementador refez cada mutação e mostrou o vermelho.
Duas escolhas dele que ficam valendo para as sprints seguintes:

- **Uma resposta só para "coluna faltando".** `quantity` ausente passou a
  levantar `MalformedBenefitError` em vez de virar `1` calado. A forma silenciosa
  **inventava dinheiro** numa parcela que compõe a base, contradizendo a regra
  que o módulo declarava três linhas acima para o `rate`.
- **`hired_on > on` sai pelo mesmo recorte do vínculo**, não por exceção dentro
  da soma — a regra escrita duas vezes é a que diverge. `without_salary` passou a
  significar uma coisa só: estava na casa em `on` e não tem faixa salarial.

⚠️ **E um mea culpa de método que vale mais que o acerto:** a primeira mutação do
arredondamento deu **14 failed**, e ia ser reportada como prova. Era `NameError` —
o símbolo não estava importado. **Mutação que quebra o import não prova asserção
nenhuma**, prova que o módulo não carrega. Refeita, deu 1 failed na asserção
certa, com o diff de centavo. O número inflado era mais bonito e teria passado.

### As outras duas decisões do dono, 06/09

**A porta de criação da primeira vigência entra no S3.** `POST
/dp/beneficios/planos` e `/tarifas` não existem, e `reajuste` exige faixa aberta
para reajustar — `app.benefit_plan` e `app.transport_fare` nasceriam e ficariam
vazias. ⛔ **S3 abre com isso no escopo dele**, que é quem consome tarifa; S1
fecha sem elas.

**A dupla faixa aberta trava só nos tipos que compõem a base.** Nada impedia duas
faixas abertas do mesmo `(colaborador, tipo)`, e a soma pega todas as vigentes —
a mesma ajuda de custo contada duas vezes, calada. VT e os demais **continuam
podendo repetir**, porque duas linhas de VT são legítimas. ⚠️ O mecanismo é
questão de engenharia e não da decisão: o predicado de índice parcial só enxerga
colunas da própria tabela, e `composes_base` mora em `app.benefit_type` — a
verificação disso ficou com quem implementa, com ordem de medir em vez de
aceitar.

## A rodada de migration — e a armadilha que "prefira o índice" quase criou

As três decisões do dono entraram em `20260906120100_dp_benefit_catalog.sql`.
Backend estável em **439 passed**, ruff limpo.

### O achado técnico que vale além desta etapa

O despacho dizia: *"o predicado de um índice parcial só enxerga colunas da própria
tabela — mas **meça em vez de aceitar a minha palavra**. Se houver forma de índice
que funcione, prefira o índice."* As três formas, medidas:

| Tentativa | Resultado |
|---|---|
| predicado citando `bt.composes_base` | `ERROR: missing FROM-clause entry for table "bt"` |
| predicado com subconsulta | `ERROR: cannot use subquery in index predicate` |
| predicado com função de lookup declarada `immutable` | **o índice é criado** — e é a armadilha |

⛔ **A terceira parece funcionar e não funciona.** O índice é criado sem
reclamação; virando `composes_base` de `false` para `true` e inserindo a terceira
faixa aberta do mesmo par, **as três sobrevivem** — o índice não reavalia o
predicado de linha que já entrou, e a mentira sobre imutabilidade só cobra no dia
em que o cliente usa a tela.

📌 **A forma da instrução é que produziu a medição.** Tivesse ela vindo como fato
("prefira o índice"), o S1 teria entregue uma trava que só falha em produção,
meses depois, sem sintoma. Vale como padrão de despacho desta etapa: quando quem
orquestra tem uma hipótese técnica, ela vai como hipótese a medir, nunca como
premissa a obedecer.

Saiu, então, **gatilho `before insert or update`** restrito a `composes_base`, com
`errcode = 'unique_violation'` — o mesmo código que o índice de `benefit_plan`
levanta, para não haver dois códigos para um choque só.

✅ **Com `pg_advisory_xact_lock` no par (colaborador, verba), decisão do
orquestrador.** Gatilho **não é** índice único: duas transações concorrentes
fariam o `exists` cada uma antes de a outra confirmar, e as duas passariam.
Entregar isso chamando de trava seria substituir uma garantia à prova de corrida
por uma que não é, no caso em que o dano é dinheiro na folha base. Nada grava
`app.employee_benefit` até S3/RH — a corrida não é impossível, é **futura**.

### Oito sabotagens, e duas que ensinaram algo

As garantias novas foram provadas uma a uma: gatilho ausente, `after` em vez de
`before`, só `insert`, existe-e-não-recusa, **recusa-demais (barra o VT)**, não
libera após fechar, policy voltando a `has_tenant`, e `can_see_domain` com o
domínio errado (`pii`). ⚠️ A quinta é a que importa tanto quanto a quarta: **uma
trava que barra o legítimo é pior que a ausência dela**, e duas linhas de vale
transporte são legítimas.

### 🔴→✅ O quarto falso verde da sprint foi escrito por quem caçava os outros

As sabotagens D e E passaram **verdes** na primeira rodada. Causa: a prova viva
reusava uma `app.company` existente porque `app.employee.company_id` é `not
null` — e o banco do `db-test` tem **1 tenant e 0 empresas**. A prova pulava,
calada, **no único ambiente que a executa**.

📌 O que a pegou não foi releitura: foi a sabotagem voltar verde e o verde ser
tratado como suspeito em vez de como resultado. `0 empresas` no banco de ensaio
não é coisa que se note lendo código. **A mutação precisa ser rotina, não zelo.**

### A colisão que o implementador não resolveu sozinho, e fez certo

`scripts/98_teste_isolamento_tenant.sql:645` — a asserção do guardião que
registra a lacuna medida (*"o catálogo NÃO filtra por domínio — `hr` passa na
policy"*, esperando `1`) passou a reprovar com `obtido 0`, porque `0` é a
correção funcionando. O comentário do próprio guardião previa: *"trocar o `1` por
`0` aqui é a correção, e ela é migration nova."*

⚠️ **E não é troca de um caractere.** Com `0`, o rótulo afirma o oposto do que
mede — a asserção **muda de natureza**: deixa de registrar lacuna e passa a
garantir que o domínio é exigido. Rótulo, comentário e valor mudam juntos, e quem
faz é o dono do arquivo. O implementador mediu o efeito (virou, rodou, restaurou)
e conferiu o `sha256` contra o original antes de devolver — padrão a repetir
sempre que alguém mexer num arquivo alheio para medir.

## S1, ciclo 2 — aprovada pelos dois, e a re-revisão mediu em vez de reler

`code-reviewer`: **APROVADO**. `guardiao-de-superficie`: **APROVADO**. Ciclos: 2
de 3.

Desta vez o revisor rodou os três portões ele mesmo — `SUÍTE COMPLETA OK`, 439
backend, 387 frontend, ruff limpo, dicionário estável, árvore intacta ao fim. E
**refez as cinco mutações na forma sutil**, não na caricatural: removeu só a
metade `terminated_on` do vínculo, honrou `effective_from` ignorando só
`effective_to`. Todas vermelhas.

📌 **Duas observações dele que valem como padrão:**

- **O gap 1 foi resolvido melhor do que ele pediu.** Ele sugeriu o predicado
  datado; o implementador **conferiu** que `status` e `terminated_on` são ambos
  `Owner.SYNC` e ambos espelham `Funcionario.Demissao`, escritos no mesmo
  `insert` de `motor/cadastro.py` — então não podem divergir, e a troca é segura.
  Sem essa conferência teria sido um chute que funciona.
- **O dublê deixou de mentir a favor do código.** `_vinculo` passou a ramificar
  no **texto do statement**: SQL que não fala de `terminated_on` faz o fake
  aplicar o recorte por estado atual, e o teste fica vermelho. Era a objeção do
  ciclo 1 — um fake que filtra por conta própria nunca contradiz a consulta.

### O quinto falso verde: a fixture do `98` divergia da matriz do produto

Achado do guardião, **contraditado em parte pelo revisor** — que foi o pedido.

A fixture zerava `compensation` para todo papel fora de `owner`/`personnel`; a
semente da migration 02 dá o domínio a **quatro** (`owner`, `personnel`,
`executive`, `accounting`). Enquanto `compensation` só guardava dado por pessoa a
divergência dormia; desde 06/09 ele guarda a leitura do catálogo, e aí ela
esconderia a pergunta que importa: *o aperto trancou fora quem concilia a folha?*
A asserção "`accounting` é barrado no catálogo" ficaria **verde no teste e falsa
em produção**. Conserto confirmado necessário pelos dois.

⚠️ **Mas o revisor foi célula a célula e a matriz continua encolhida para o
`hr`** — `pii`, `health` e `disciplinary` estão `f` na fixture e `t` no produto.
Não produz falso verde hoje (nenhuma asserção exercita `hr` contra os três), e é
armadilha latente: `hr` é justamente o papel de PII, então a primeira asserção
sobre `hr` e PII nasce falsa.

📌 **E ele nomeou a classe, que é o que importa:** o padrão adotado é *remendar um
domínio por vez* — `banking` em 05/09, `compensation` em 06/09, `hr` ainda não
porque ninguém precisou. **Três remendos são um sintoma.** Trocar a semente
genérica do `98` pelo mesmo `case` da migration 02 mata a classe e torna os dois
blocos de override desnecessários; `supabase/seed.sql` já faz assim e está
correto. Item próprio.

### A lacuna do flip de `composes_base` — confirmada, com o caminho de volta medido

O revisor confirmou a medição do guardião e acrescentou dois fatos que ela não
tinha:

| Passo medido | Resultado |
|---|---|
| flip de `transport_voucher` para `composes_base = true` | as 2 faixas abertas **sobrevivem** |
| `update` numa das sobreviventes | **recusado** — o estado se denuncia |
| `update` fechando uma delas | **aceito** — o caminho de recuperação existe |

O gatilho retorna cedo quando `new.effective_to is not null`, então **fechar é
sempre permitido**: o estado não encrava e a próxima escrita qualquer o anuncia.

📌 **Não bloqueia o S1, e por um motivo mais forte que "é pequeno": o S1 não
entrega rota nenhuma que escreva `benefit_type` nem `employee_benefit`.** As seis
rotas de `/dp` são conta, três de posto, catálogo (leitura) e reajuste (que toca
`benefit_plan`/`transport_fare`). Virar `composes_base` hoje só acontece por SQL
direto — a superfície do produto não alcança a lacuna. Ela vira real no sprint que
entregar a **tela de catálogo**, e é lá que o conserto pertence, como gatilho em
`app.benefit_type` que confere antes de deixar o flip passar. **Fechar isso agora
seria escrever a trava longe da porta que a exige.**

### Resíduos com endereço — nenhum bloqueia

- **R1** — a fixture do arredondamento **não distingue nada**: 1750 × 0,0333 dá
  58,28 tanto em `ROUND_HALF_UP` quanto em `ROUND_HALF_EVEN`, e **apagar o
  argumento `rounding=` inteiro também passa**, porque o default do `Decimal` é
  `HALF_EVEN` — que é justamente a alternativa que o comentário do módulo
  rejeita. Correção de um dígito (`rate="0.0331"` → 57,925 → 57,93 vs 57,92),
  despachada em 06/09.
- **R2** — o predicado datado do vínculo está coberto na **presença**, não na
  semântica: invertê-lo para trazer só quem já saiu passa 46 de 46. 📌
  **Recomendação para S3:** o vínculo *é* uma vigência, e `in_effect(on,
  hired_on, terminated_on)` já existe no módulo — movê-lo para Python o põe sob a
  mesma cobertura de todo o resto e apaga a regra escrita duas vezes, que é a
  decisão de desenho que o próprio S1 declarou para preço.
- **R3** — a guarda de tautologia tem uma terceira fuga (`(tenant_id = ...) or
  (1=1)`) fora das duas declaradas. Não é acidente plausível — o erro real, sem
  parênteses, é pego. É precisão de docstring, despachada junto com R1.

✅ **Os três fechados em 06/09.** A fixture passou a `rate="0.0331"` (57,925 →
**57,93** em `HALF_UP` e **57,92** em `HALF_EVEN`, `DOWN` e sem argumento), e as
**três** mutações ficam vermelhas — inclusive a remoção do `rounding=`. O
comentário de `_money` foi corrigido junto: ele nomeava `ROUND_DOWN` como a
mutação a temer, que era o mesmo auto-engano do teste. O docstring do dublê passou
a listar as três fugas e a dizer **por que** a terceira fica de fora.

### 📌 A lição de método do S1, e ela não é sobre benefícios

O implementador nomeou, ao fechar: *"minha mutação `ROUND_DOWN` ficou vermelha e
eu li aquilo como 'a asserção tem dentes'. Tinha dentes para a substituição
grosseira e nenhum para a remoção — e a remoção é a regressão que de fato
acontece, porque `rounding=ROUND_HALF_UP` parece verbosidade."*

⛔ **Mutação escolhida por quem escreveu o código herda o ponto cego de quem
escreveu o código.** Ele mutou o que sabia estar lá; o revisor mutou **a
ausência**. Foi o mesmo padrão nas cinco mutações do ciclo 2, refeitas na forma
sutil em vez da caricatural — e é o que separa mutação como rotina de mutação
como zelo. Vale para S3, S4 e S5: a mutação que conta é a que o autor não
escolheria.

## Antes do S3 — o gate não podia fechar, e a SPEC §1e afirmava algo falso

Medido em **06/09/2026**, antes de despachar. O S3 é o sprint que aposenta o
legado e tem o gate mais exigente da etapa: *"apuração de um mês real de staging
confere com o legado linha a linha — não só no total. Divergência de uma pessoa é
falha do gate."*

### O que a medição mostrou

| Onde | Estado em 06/09 |
|---|---|
| **staging** (`wbzaqjlfpqteesehapnn`) | 0 colaborador, 0 unidade, 0 `leave_period`, 1 tenant — **vazio**, e o gate nomeia staging |
| **produção** | 176 colaboradores, 27 unidades, 5 empresas, 6.395 `expected_workday`, **821 desvios** |
| produção · `app.leave_period` | **0** |
| produção · `app.employee_compensation` | **0** |
| repositório | **nenhum export do legado** para conferir contra |

⚠️ **E uma nota de projeto virou falsa no caminho:** até 04/09 o domínio de
produção estava em zero e o motor nunca tinha rodado lá. **Entre 04/09 e 06/09 o
motor rodou** — `app.sync_run` foi de 5 para 271. ✅ **A regra 8 está respeitada, e
foi conferida e não presumida:** os 821 desvios estão **todos** em `mode =
'shadow'` (29/08 a 04/09), e `app.alert_queue` e `app.report_cycle` estão em
**zero**. Nada foi entregue a gestor nenhum.

### 🔴 A SPEC §1e mandava ler uma coluna que não pode responder

*"Os dois leem `app.leave_period` com `category` de falta injustificada."* O check
da coluna aceita `('vacation','leave_period','leave_of_absence','suspension')` — e
**nenhum deles é falta**. Não é descuido: o comentário da tabela declara *"rótulo
neutro por decisão de produto; motivo de leave_period é dado de saúde e não é
capturado"*.

📌 **É o mesmo padrão da §1b na S2**: a frase se falsifica lendo o repositório, e
a sprint teria transcrito uma instrução impossível. Corrigida na SPEC.

### Onde a falta vive de verdade — e por que ela não basta

Espelho de produção, 62 afastamentos:

| `JustificativaNome` | Linhas | Período |
|---|---|---|
| Férias | 43 | 07/2024 → 09/2026 |
| Atested | 13 | 06/2025 → 04/2026 |
| ATEST M | 4 | 03/2026 → 08/2026 |
| AFASTAD | 1 | 07/2026 |
| **FALTA** | **1** | **30–31/08/2025** |

⚠️ **A distinção existe só como texto livre.** `AfastamentoId` foi conferido e é
identificador de registro — **62 distintos em 62 linhas** —, não código de tipo.
Sobra o `JustificativaNome`, digitado no Secullum do cliente e truncado em 7
caracteres: `Atested` e `ATEST M` são o mesmo conceito escrito de dois jeitos.

⛔ **E existe UMA falta em 26 meses.** Mesmo com toda a canalização pronta, a
reconciliação de um mês recente compararia **zero faltas contra zero faltas**: o
gate passaria sem provar a única regra que a SPEC chama de mais perigosa.

### As duas decisões do dono, 06/09

**1. Promover o espelho com curadoria.** `secullum."FuncionarioAfastamento"` →
`app.leave_period`, com mapa `JustificativaNome` → categoria e migration nova
acrescentando a categoria de falta ao check. A regra é a de
`app.payroll_event_map` (migration 30), que já resolve exatamente este problema:
**string não curada não entra em cálculo — falha alto em vez de virar "sem
falta"**. Silêncio aqui não é neutro: ele dá VT a quem faltou.

**2. O gate vira reconciliação + falta sintética.** A reconciliação linha a linha
roda sobre o mês real (janela, dias úteis, tarifa, total); **a regra de falta é
exercitada por fixture sintética** com casos construídos — falta no mês civil
anterior, admissão no meio do período, desligamento no meio. Prova o mecanismo
sem depender de o cliente ter faltado.

⛔ **O que continua faltando, e não é código:** um **mês fechado do legado** para
a metade da reconciliação. Sem ele a apuração é auto-consistente e não
comprovada. Fica como item de aceite **aberto** do S3 — o sprint entrega o
mecanismo provado por fixture; o "linha a linha" fecha quando o mês chegar.
Registrar como fechado sem isso seria o falso verde que esta etapa passou o S1
inteiro caçando.

## S3, ciclo 1 — a porta que paga não exigia o ciclo congelado

`code-reviewer`: **REPROVADO**, ciclo 1 de 3. Portões conferidos: **501 passed**
(era 439), ruff limpo em 92 arquivos, `SUÍTE COMPLETA OK` com 45 migrations.

### 🔴 O achado ALTO, e ele desmonta a própria maquinaria da sprint

`routers/dp.py` não guarda `status` em nenhum ponto do caminho de export. Medido
ao vivo, e reconferido depois contra a árvore restaurada:

```
status do ciclo: draft · HTTP 200 / 200
arquivo 1: 1001;Ana Ribeiro;341;0001;987654321;checking;161.50
arquivo 2: 1001;Ana Ribeiro;341;0001;987654321;checking;1881.00
```

**O mesmo ciclo, a mesma pessoa, dois arquivos de banco diferentes**, porque
reapurar um rascunho apaga e reinsere as linhas — depois de a primeira remessa já
ter saído.

📌 É literalmente o que o docstring do congelamento diz que não pode acontecer:
*"reapurar aqui deixaria o número da tela e o número da remessa dependerem de o
dado não ter mudado no meio"*. **Toda a maquinaria de imutabilidade — gatilho,
garantia, sessenta linhas de justificativa na migration — protege o ciclo
congelado, e a porta que paga não exige que ele esteja congelado.** E o teste do
caminho feliz exporta de um rascunho: **o teste que existe é o defeito.**

### 🔴 O segundo ALTO é reincidência exata do ciclo 1 do S1

`_vinculo_na_janela`: apagando o recorte de `terminated_on`, os **62 testes
passam**. O teste que deveria pegar não pega porque a fixture já entrega a escala
terminando no fim do mês — a redução vem da escala, não do recorte. O par do lado
da **admissão** existe e é forte; o espelho dele nunca foi escrito. `_cobertura`
tem a mesma assimetria.

📌 Terceira vez nesta etapa que uma metade de uma regra datada fica sem asserção
enquanto a outra tem. **Vale como item de checklist para S4 e S5: toda regra com
duas pontas precisa das duas asserções, e a que falta é sempre a de baixo.**

### O que o revisor atacou e NÃO achou defeito

- **A união das duas fontes de falta está correta.** Mutou `merge_absence_days`
  para somar por fonte em vez de unir por dia → vermelho, com o positivo ao lado
  (`fontes diferentes somam dias diferentes`). ⚠️ E a assimetria é o que torna a
  recusa possível: o espelho é lido **cru** (a curadoria classifica em Python)
  enquanto o domínio já vem curado e pode filtrar no `where`.
- **Cinco das seis regras de leitura são transcrição fiel**, incluindo a recusa
  quando `expected_workday` não cobre o vínculo: *"dia sem linha não é dia sem
  expediente; tratá-lo como zero paga a menos sem sintoma"*.
- **A conta bancária não escapa** por log, mensagem de erro, nome de arquivo nem
  trilha — os quatro caminhos conferidos. A remessa exige `banking` e,
  corretamente, **não** exige admin: `accounting` confere sem apurar.
- **Os dois resíduos do S1 foram fechados de verdade** — reaplicou a mutação que
  passava verde no ciclo 2 do S1 (apagar o `rounding=`) e agora ela fica vermelha.

### ✅ A janela de falta da cesta — confirmada pelo dono

Era o único item que o revisor marcou como **interpretação, não transcrição**: a
SPEC escreve a janela só para o VT e o `ANEXO` §4.2 não nomeia o período da
cesta. ✅ **Dono, 06/09: a cesta conta no mesmo mês civil anterior que o VT.** Uma
regra só para as duas rotinas — a segunda cópia é a que diverge. Nenhum código
muda; o que muda é o estatuto da linha.

## ⛔ Incidente de 06/09/2026 — um revisor destruiu um arquivo não versionado

O `code-reviewer`, ao restaurar `backend/operax/dp/beneficios.py` depois de uma
mutação, **copiou por cima a versão do S1** em vez da do S3. Arquivo não
versionado: o git não recupera.

**Medido por quem orquestra, não aceito do relato:** 705 linhas, zero ocorrências
dos cinco símbolos do S3, `3 failed / 498 passed`. O `.pyc` foi recompilado a
partir da versão errada — `strings` nele não acha nenhum símbolo. Sem recuperação
por ali. O `find` do revisor achou três caminhos e os três eram **o mesmo inode**
(vistas de WSL, não cópias).

✅ **Resolvido:** o implementador reescreveu os cinco símbolos a partir dos três
testes vermelhos, que sobreviveram e serviram de especificação. O arquivo voltou
com **as duas camadas** — as correções do S1 (arredondamento, vínculo datado,
`quantity`) e a superfície do S3 —, e o revisor conferiu marcador por marcador.
501 passed.

### 📌 A causa é de desenho, e é de quem despacha

Um revisor com ferramenta de escrita, mutando arquivos **não versionados** para
medir, é uma armadilha montada no despacho — não um descuido dele. Três coisas
mudam a partir daqui:

1. **Quem muta arquivo alheio confere o `sha256` contra o original ao restaurar.**
   O implementador do S1 já fazia isso por conta própria em 06/09; passa a ser
   instrução no despacho, não virtude individual.
2. **Trabalho aprovado é commitado antes de a próxima sprint começar.** O S1
   estava aprovado e não versionado quando o S3 começou; se estivesse em git, o
   estrago seria `git checkout` e não uma reescrita.
3. ✅ **O revisor reportou o próprio estrago em primeiro lugar**, com a superfície
   exata para restaurar, e reconferiu os dois ALTO contra a árvore restaurada para
   o veredito não repousar em medição feita sobre o arquivo quebrado. É o
   comportamento certo, e é o que tornou o incidente barato.

## S3 aprovado — e o critério de despacho que o guardião derrubou

`code-reviewer` **APROVADO** (ciclo 2). `guardiao-de-superficie` **APROVADO**, na
segunda passada. ✅ **As cinco policies de RLS autorizadas pelo dono em 06/09**,
como estão.

**Passada final do guardião, com a árvore congelada por hash ANTES de medir:**

```
ANTES : e25f6b46…  DEPOIS: e25f6b46…   >>> os dois portões mediram a MESMA árvore
db-test exit=0 · 357 asserções · SUÍTE COMPLETA OK · 519 passed
```

### 🔴 O item 7 do despacho era inenunciável — e a causa vale para S4 e S5

O critério que **quem orquestra** escreveu (*"supervisor não vê ciclo de outra
unidade e vê o da dele"*) **não tem como ser verdadeiro** nas tabelas do S3, e o
guardião o derrubou com medição. O revisor conferiu as três premissas na fonte:

1. `unit_supervisor` **não tem domínio sensível nenhum** — `compensation` já o
   barra, então ele não vê a linha da unidade dele **nem** a da outra.
2. `app.benefit_cycle` **não tem coluna de unidade** — o ciclo é do tenant, e
   "ciclo de outra unidade" não existe como objeto.
3. 📌 **A que fecha o argumento:** `util.can_see_employee` e `util.can_see_unit`
   **curto-circuitam em `util.is_admin`**. Para `owner`/`hr`/`personnel` o eixo de
   unidade é **inerte**. Sobra **um** papel no produto em que ele decide algo
   nestas tabelas: `accounting`.

A reenunciação pelo `accounting` não é troca de conveniência — é o único lugar
onde a pergunta tem resposta. Medida com controle, dentro de savepoint:

```
com escopo do tenant, LÊ A Centro (1) e A Norte (1)     <- o positivo
recortado em A Centro, VÊ A Centro (1), NÃO vê A Norte (0)  <- o eixo discrimina
o CICLO não tem eixo de unidade: segue visível (1)      <- a assimetria, declarada
desfeito o recorte, A Norte volta (1)                   <- o controle
```

⚠️ **E ele não abandonou o supervisor** — aplicou-o em `app.work_post`, onde é
expressível, e no S3 enunciou a verdade (*"não vê nem o da unidade dele"*) em vez
da meia-verdade, que seria verdadeira e vazia.

📌 **A forma geral, para não redescobrir em S4 e S5:** *o eixo de unidade é
exercido pelo papel que tem o domínio da tabela **e** não está na lista curta de
`util.can_see_unit`. Se nenhum papel satisfaz as duas coisas, a tabela **não tem**
eixo de unidade e o item é inaplicável — **declare isso** em vez de escrever um
par impossível.*

### ⛔ Dois dos cinco motivos da reprovação eram de quem orquestra

O guardião reprovou por cinco motivos, todos bem medidos. **Dois não eram de quem
implementou, e ele não tinha como saber:**

1. *"Entregou vermelho"* — os três testes falhando eram os que o **revisor**
   derrubou ao destruir `beneficios.py`. O implementador entregou com **501
   verdes**. Medição certa, atribuição impossível.
2. *"A árvore se moveu sob o gate"* — quatro arquivos de produção mudaram durante
   as medições dele porque **quem orquestra despachou guardião e revisor em
   paralelo e ainda mandou o implementador corrigir enquanto ele media.**

📌 **E o achado de método da rodada é dele:** *mtime não serve de registro de
mudança* — o de `beneficios.py` era **anterior** ao `grep` que provou a ausência
do símbolo. **Congelar por hash antes de medir** passa a ser instrução no
despacho, e foi o que ele fez na segunda passada.

Os motivos 3 e 4 (zero asserção no `98`/`99`; varredura de conta em 3 de 11 rotas)
ele mesmo corrigiu — 58 asserções e `test_dp_gate_s3.py` —, e **pediu que fossem
revistas por outro**, que é o pedido certo. O revisor mediu por diferença: o `98`
tinha **110** no S1 e tem **168** agora; delta de 58, `700 / 0`. Aprovadas.

### A pergunta que fica registrada como decisão, não como acidente

✅ **Dono, 06/09: as cinco policies ficam como estão.** `leave_justification_map_admin`
é `ALL` + `is_admin` — **`app.payroll_event_map` palavra por palavra**, conferido
na fonte pelos dois revisores.

⚠️ **Consequência declarada:** `accounting` tem `compensation` e **não lê o mapa
que classificou as faltas da folha que ele concilia**. Em `payroll_event_map` isso
é inócuo porque lá o conferente não é auditado contra o mapa; aqui a curadoria
decide quem perde cesta e quantos dias de VT cada um recebe. Fica revisável
quando o `accounting` precisar auditar a curadoria — e fica **escrito**.

### O que o S3 NÃO fechou, e está declarado

- ⛔ **A reconciliação linha a linha contra o legado continua ABERTA** — falta o
  mês fechado do cliente. Não foi fechada por baixo, e nenhum legado sintético foi
  inventado. Conferido pelo revisor.
- ⛔ **S3 nasce inerte em produção, por dois bloqueios independentes:**
  `app.leave_justification_map` nasce vazia e **não há rota para curá-la**; e
  `app.expected_workday` cobre ~6 dias, então a apuração de VT **recusa**. ✅ O
  revisor confirmou que recusar é o comportamento certo: *"dia sem linha não é dia
  sem expediente; tratá-lo como zero paga a menos sem sintoma"*.
- A metade de frontend (`frontend/src/app/dashboard/dp/`) não foi despachada.

## Despacho do S4 — três coisas medidas antes, e duas mudaram o escopo

**1. ✅ Superfície de `public` autorizada pelo dono (06/09), só agregado.** É a
parada declarada do `CLAUDE.md`, e ela não foi presumida.

**2. ⛔ `public.fn_dp_panel` não é criada — o painel vai pelo Caminho 2.**
Decisão do dono. A folha base **já existe em Python** desde o S1
(`beneficios.compute_base_payroll`), e o S1 declarou que a regra de vigência mora
lá porque *"escrita nos dois lugares ela divergiria, e a metade SQL é a que o
pytest não alcança"*. Uma RPC que recalculasse a mesma soma em SQL seria a regra
escrita duas vezes — e o `ANEXO` §2a exige que a folha base **bata com a do
cliente na vírgula**.

📌 E é coerente com o Contrato: folha base é `compensation`, e o Caminho 1
carrega **só agregado não sensível**. `public.fn_dp_alerts` fica, porque contagem
de documento a vencer não é dado de pessoa.

**3. ⛔ `public.vw_unit_compliance` desce para o S5.** Ela lê
`app.unit_compliance_report` — a tabela que o **S5** cria. Conferido em 06/09:
não existe em migration nenhuma. O `SPRINTS-DP.md` já listava só as duas RPCs e
estava certo; a `SPEC-DP.md` §1k é que estava à frente do próprio plano, e foi
corrigida.

**O que foi conferido e estava certo:** `app.document_type.expiry_alert_days`
existe desde a migration 08 (`integer not null default 30`), então o gate *"os 8
contadores usam a coluna, não constante"* é satisfazível.

⚠️ **E o gate do S4 herda o problema do S3:** *"os 9 KPIs batem com o legado
sobre a mesma base"* — e **não há export do legado no repositório**. Os 9 KPIs
estão enumerados no `ANEXO` §2a com as fórmulas declaradas na tela, então o
sprint pode transcrevê-las e provar por fixture; a **conferência contra o legado
fica ABERTA**, como no S3, até o mês fechado do cliente chegar.

⚠️ **Retenção é canetada de produto, não de engenharia.** O `ANEXO` §2a já
registra que `ativos / total no filtro` **não é retenção** — muda de significado
conforme o filtro. O S4 **transcreve a fórmula do legado** (é o que o gate
compara) e não a conserta; o rótulo é decisão do dono, pendente.

## S4 aprovado — e a cobertura saiu de 9/21 para 40/41

`guardiao-de-superficie` **APROVADO** no ciclo 1. `code-reviewer` **REPROVADO** no
ciclo 1 com doze achados, **APROVADO** no ciclo 2. Portões: **584 passed**, ruff
limpo, `SUÍTE COMPLETA OK` com as 49 migrations.

📌 **A medida que resume o ciclo:** no ciclo 1, **12 de 21 mutações sobreviviam**.
No ciclo 2, o revisor refez **41 mutações próprias** e **40 morreram** — a única
sobrevivente é o predicado que a migration e o `87` agora **declaram** como defesa
em profundidade (`util.can_see_employee` é preso a `app.tenant_member` e barra
sozinho, então nenhuma fixture consegue fazer o outro morder).

### O método que mudou, e veio do revisor

⚠️ **Ele subiu um Postgres descartável próprio** (container e porta próprios) em
vez de disputar o `operax_test`. **Isso resolve a colisão que custou dois motivos
de reprovação no S3** e que vinha sendo contornada por sequenciamento. Passa a ser
a forma recomendada de despachar revisor e guardião juntos.

⚠️ **E ele entregou as somas `md5` da árvore que aprovou.** Conferi as nove antes
de commitar: batem. O veredito passa a valer para uma árvore identificável, e não
para "o que estava lá quando eu olhei" — que é exatamente o que faltava quando a
árvore se moveu sob o gate no S3.

### Três decisões do implementador que valem além do S4

**1. Prazo de férias vencido CONTA**, e o argumento é de direção, não de gosto:
sem o piso em `current_date`, quem já estourou o prazo — onde o empregador passa
a dever em dobro (CLT art. 137) — aparece. *"Se o legado o exclui, a divergência
ACRESCENTA gente ao alerta e nunca some com ninguém."* ✅ O revisor confirmou a
assimetria: **falso positivo custa uma conferência; falso negativo custa o
pagamento em dobro.**

**2. A regra saiu do SQL em vez de ser copiada no dublê.** Dois `status` sem
teste seriam "cobertos" ensinando o dublê a decidir — que é como um teste vira
cópia da regra em vez de prova dela. Ele moveu a decisão para o Python, e o dublê
voltou a não decidir nada. É o precedente que `beneficios.in_effect` abriu no S1.

**3. Ele remediu antes de reescrever, e achou o gêmeo.** No item do eixo de
tenant, em vez de só corrigir o comentário apontado, refez a medição — e
descobriu que **o mesmo exagero estava no passo 4 da garantia da própria
migration**. Dois textos prometiam um eixo que nenhum dos dois media.

### 🔴 A guarda de PII do `99` falava dois vocabulários — e o mais fraco era o permanente

Achado do revisor no ciclo 2, medido: o item 8 (colunas de view) enumera
`mother_name|father_name|race_color|dependents|…`; o item 9 (retorno de função
definer) usava `\mname\M`. **`_` é caractere de palavra no regex do Postgres**,
então `mother_name`, `father_name` e `dependents_names` **não casavam**, e
`race_color` nem estava na lista. Uma função definer de `public` devolvendo
qualquer uma das quatro passava verde.

📌 **A correção não foi sincronizar as duas listas — foi haver uma só.**
`pg_temp.pii_regex()` é a fonte, e os dois itens a chamam: duas listas que
precisam concordar e podem divergir sempre divergem. Provado por sondagem: as
quatro colunas agora reprovam, e removidas as sondas o `99` volta verde **por
mérito**. E o limite que a varredura **não** alcança ficou declarado no arquivo:
`returns json`, `jsonb` e `setof record` não têm nome de coluna em
`pg_get_function_result`.

### O que o S4 NÃO fechou, e está declarado

- ⛔ **A reconciliação dos 9 KPIs com o legado continua ABERTA** — mesmo motivo do
  S3: não há mês fechado do cliente no repositório. Nenhum legado sintético foi
  inventado.
- ⏳ **Documento × pessoa:** `document_expired` e `document_expiring` contam
  **documento**; os outros seis contam **pessoa**. O `ANEXO` §2c não fecha, e com
  CNH (uma por pessoa) as duas leituras dão o mesmo número — por isso a tela do
  legado não resolve. Reportado ao dono, **com o número fixado no `87`**: o dia
  em que a decisão vier, o teste fica vermelho e a mudança é deliberada.
- ⏳ **O legado rotula dois cartões como "CNH" e a função não.**
  `app.document_type` não tem `code` — a identidade é o `name`, texto livre por
  tenant. Um `ilike 'cnh%'` poria regra de negócio numa string e erraria
  **calado** no tenant que chamasse o tipo de "Carteira de Habilitação".
- ⏳ **Retenção** segue transcrita do legado e não consertada — canetada do dono.
- A metade de frontend do S4 foi despachada depois, junto com as de S1 e S3,
  e revisada em bloco — ver a seção seguinte.

## O frontend do DP — a primeira revisão que um frontend desta etapa recebeu

S1, S3 e S4 nasceram só com a metade de backend. As telas das três foram escritas
depois e revisadas de uma vez. **Ciclo 1: REPROVADO**, seis achados — 2 ALTO,
3 MÉDIO, 1 BAIXO.

### 🔴 Os dois ALTO são a mesma história: a tela ignora o que o backend construiu para ela

Os dois caem em cima do commit `831cb52`, cuja mensagem é literalmente *"a remessa
passa a ser alcançável, e o ciclo congelado deixa de sumir no F5"*. O frontend
escrito em cima dele não chamava nem uma coisa nem outra.

**ALTO 1 — a parede reerguida uma porta adiante.** `dashboard/dp/ciclos/page.tsx`
exigia papel administrativo (`isAdmin`). Mas quem confere a remessa é
`accounting`, que tem `compensation` e **não** é admin; e `hr` é admin e **não**
tem `compensation`. A lista de papéis errava nos dois sentidos. O backend tinha
tirado a exigência de admin de `GET /dp/ciclos` de propósito, e escreveu o motivo
na própria docstring: *"exigir admin aqui devolveria a mesma parede uma porta
adiante"*. A tela devolveu.

⚠️ **E o seed de dev não tem `accounting` nem `hr`** — teste manual nenhum
encontraria isso. Ou o teste automatizado prova o par, ou nada prova.

**ALTO 2 — o caminho que duplicava a competência.** `GET /dp/ciclos` não era
consumida em lugar nenhum: o ciclo vivia só em `useState`. Depois de um F5 a tela
dizia "Nada apurado" para um mês já gerado, e a única ação oferecida era apurar —
que **insere uma segunda linha**, porque `save_draft` procura rascunho *aberto*,
acha só o `generated`, e o `unique` da competência inclui o `status`. O operador
passava a ver "Rascunho" e a frase "o arquivo do banco exige o ciclo gerado" para
uma competência que já estava gerada, **e a remessa que ele congelou ficava
inalcançável**.

### O terceiro achado é um comentário que se tornou falso e levou o tipo junto

`queries.ts` carregava quinze linhas explicando que `can_export_remittance`
*"ainda não é enviado pelo backend"*. Ele estava no contrato desde o mesmo commit,
obrigatório e não-nulo, nos dois schemas. Por causa da crença, o campo tinha sido
declarado opcional — e um campo opcional contra um contrato obrigatório transforma
uma renomeação no backend em `undefined` silencioso: o botão de remessa sumiria
para sempre, **sem um erro de tipo em lugar nenhum**.

📌 A regra que sobreviveu à correção não é a do tipo, é a da leitura: **ausência
vale "não pode", nunca "pode"** — e ela continua exercida por teste que apaga a
chave em runtime, porque o que chega é JSON, não tipo.

### O que o revisor mediu e NÃO achou defeito

Vale tanto quanto o que ele achou. Ele foi ao ambiente vivo conferir o Caminho 1:

- `fn_dp_alerts` como `anon` → **401**; autenticada → só `(code, total)`, 8 linhas,
  zero PII.
- **Como supervisor → 4/5/3, contra 26/25/18 do DP.** O recorte está na função; o
  cliente não envia nada. É a prova de que a RLS responde, não a tela.
- O botão de remessa é **ausência do DOM**, não `disabled`.
- 11 mutações, 11 mortas, nenhum falso verde.

### Ciclo 2 — e a confissão que vale mais que o resultado

Portões conferidos por mim, não só relatados: **32 arquivos / 522 testes**
(era 31/494), `prettier --check` limpo, `tsc --noEmit` exit 0. Mutação: **34
aplicadas, 34 mortas**.

📌 **Duas sobreviveram na primeira passada (M29 e M34), e a causa é uma armadilha
de método que não é sobre benefício nenhum:** o não-escritor só tinha sido testado
**contra competência congelada** — onde o próprio congelamento já esconde os
botões. O teste era **verde sem provar nada** sobre `canWrite`. É falso verde da
terceira família: *a asserção passa por causa de outra condição, não da que ela diz
medir*. Corrigido isolando `canWrite = false` **sobre um rascunho**, nas duas
camadas.

### A correção do ALTO 1 mudou a navegação, e isso não foi pedido

"Painel de DP" saiu do bloco Administração para uma seção sempre visível — e ela
pode ser sempre visível porque a página abre para qualquer membro do tenant: quem
alcança `compensation` recebe os nove KPIs, quem não alcança recebe os oito
contadores do cadastro recortados pela RLS. **Ninguém vê "nada", então ninguém
precisa ser excluído** — e `accounting`, que não está em `HR_ROLES`, deixa de ficar
sem porta.

"Ciclo mensal" saiu da barra lateral e virou link **dentro** do painel, renderizado
só quando `panel.status === "ok"`: as duas rotas avaliam `permissoes.compensation`
no mesmo `check_permissions`, então um painel `ok` é **prova** de que a tela de
ciclo abre. Nenhuma lista de papéis deste frontend acertava os dois lados —
trancava `accounting` fora e levava `hr` a um 404.

⏳ **O que desfaz isso:** `/me` devolvendo os domínios resolvidos, e não só o papel.
Aí o item volta para a barra lateral com o eixo certo.

### O que o frontend NÃO fechou, e está declarado

- ⏳ **Lacuna de contrato: não existe `GET /dp/ciclos/{id}`.** `CycleSummary` não
  traz `rows`, então uma competência lida do histórico não tem como recuperar a
  lista por pessoa. A tela modela `rows` como `null` — **e não `[]`**, que diria
  "ninguém tem direito" sobre uma competência que pode ter duzentas linhas — e
  manda conferir pelo Excel e pelo PDF. É honesto, e é provisório.
- ⏳ **A escrita continua deduzida de `isAdmin`** porque nenhuma rota de ciclo
  devolve `can_write`. `util.is_admin` é lista fixa de papéis nos dois lados, e não
  a matriz de domínios, que é dado que o cliente edita por `update` — por isso a
  cópia é tolerável aqui e não seria lá. Quando a rota devolver o campo, a linha
  sai.
- ⏳ **N+1 declarado no rollup por empresa** (~20 ms por chamada, em `Promise.all`)
  — **decisão de não corrigir**, com o contrato que o resolveria escrito no lugar:
  a quebra por empresa dentro da resposta do painel.

## S5 — aprovada, e os dois ALTO do ciclo 1 são de famílias diferentes

**Ciclo 1: REPROVADO** (2 ALTO, 4 MÉDIO/BAIXO). **Ciclo 2: APROVADO** pelo revisor e
pelo guardião. Portões medidos por mim, não relatados: `pytest` **621** (baseline
618), `ruff` limpo, `testar_migrations.sh` **SUÍTE COMPLETA OK**, 51 migrations.

### 🔴 ALTO 1 — afrouxar uma coluna quebrou o consumidor do próprio silêncio

A decisão de tornar `app.payroll_event_map.category` anulável está **certa**, e os
dois revisores a confirmaram: semear `'other'` seria o produto decidindo como o
dinheiro é somado, e como `'other'` é categoria legítima, a linha semeada ficaria
indistinguível de uma curada. A promessa não sumiu — virou
`check (validated_at is null or category is not null)`, que é **mais forte**:
validar exige classificar.

O defeito foi o fio velho ligado. `imports.fetch_mapped_codes` perguntava
`select code from app.payroll_event_map`, e a resposta era exata **enquanto**
`category` fosse `not null`: existir linha equivalia a ter categoria. A semente
insere uma linha por código com `category` nula, e o mesmo predicado passou a
responder *"o código é conhecido"* — verdade para todos. `Report.unmapped_codes`
vinha vazio e a tela de import diria **"nenhuma pendência" com a curadoria inteira
por fazer**, enquanto o contador da outra rota dizia N.

📌 **A forma do erro, e ela é maior que este caso:** mudar a semântica de uma coluna
não quebra só quem a lê — quebra **quem infere dela**. Eu procurei o consumidor e
não achei, porque olhei *o que o SQL seleciona* (só `code`) em vez de *o que o
conjunto de linhas passou a significar*.

### 🔴 ALTO 2 — falso verde dentro da prova do próprio gate, e nem eu nem o revisor acertamos o conserto

`select ... into` sem `strict` deixa o record NULL quando a consulta não devolve
linha, e `NULL <> valor` é **NULL**, que não é `true`: o `if` não dispara. Mutar a
view para devolver **zero linhas** fazia a migration passar verde, com três
asserções passando em branco.

Eu ofereci três formas de conserto. O implementador mediu que **`into strict`
sozinho não basta**, e estava certo: na semente a linha **existe** e quem é nula é
a *coluna*, então `NULL <> 'H.EXTRA 60%'` continua não sendo `true`. Usou as duas
formas. O revisor então fechou a prova nos dois sentidos, acrescentando a mutação
que faltava:

| mutante | `strict` + `is distinct from` | `into` + `<>` |
|---|---|---|
| view devolve zero linhas | 🔴 `query returned no rows` | ✅ **verde** |
| view sem o `not exists` | 🔴 `more than one row` | 🔴 |
| **cadeia com a vigente vindo 1ª** | 🔴 `more than one row` | ✅ **verde** |
| semente sem `label` | 🔴 `veio "<NULL>"` | ✅ **verde** |
| semente sem `nature` | 🔴 `veio "<NULL>"` | ✅ **verde** |

Sem a terceira linha, *"cada forma mata o que a outra não mata"* seria afirmação
sem prova. Com ela, é medição nas duas direções.

### O achado técnico da sprint: era o predicado que dava o lock errado

O `save_draft` inseria um **segundo rascunho ao lado do ciclo gerado** — defeito de
código do S3, já aprovado, achado por uma revisão de **frontend**. As quatro peças
são todas de desenho: a reserva filtrava `status = 'draft'` e contra competência
congelada achava zero; a unique inclui `status`, então a linha nova não colide; e
`trg_benefit_cycle_immutable` é `before update or delete`, então não vê INSERT.

⛔ **O que fecha a corrida é o `status` SAIR do `where` da reserva.** Sob READ
COMMITTED, `select ... for update` reavalia a qualificação contra a versão nova da
linha: com o predicado de status, o congelamento concorrente faz a linha deixar de
casar e ela **some** — quem esperava recebe zero e insere. Sem ele, a linha volta
já congelada e a guarda recusa. Medido com duas sessões e banco novo por variante.

### ⛔ E o registro desse achado estava errado — corrigido em 08/09

O comentário e a mensagem do commit afirmavam, **como fato medido**, que um gatilho
`before insert` não fecharia a corrida. O revisor mediu a terceira variante: **ele
fecha.** `gerar` congela com **UPDATE**, então o escritor toma lock de linha, quem
apura sempre bloqueia no `for update`, e ao chegar no insert já enxerga o
congelamento commitado.

O raciocínio veio **importado da `dp_unit_compliance`**, onde é correto e é outro
caso: lá a concorrência é entre dois INSERTs de renovação, que genuinamente não se
enxergam. **Argumento não atravessa de um caso para o outro só porque as duas
frases falam de gatilho.** O comportamento entregue está certo; era o registro que
estava errado, e registro errado é o que faz a próxima pessoa desenhar em cima de
uma medição que nunca existiu. Comentário e mensagem de commit corrigidos.

### O guardião: mudou quem GARANTE, não quem alcança

A leitura da curadoria trocou `user_scope` (RLS) por `tenant_scope`
(`service_role`). Medido nas **duas** tabelas que ela lê — eu só tinha olhado uma:
para `{owner, personnel}` as policies avaliam `true` em toda linha do tenant de
qualquer forma, então o conjunto é **idêntico**. Zero alcance novo.

⏳ **A ressalva, que vale mais que o veredito:** a policy era trava de banco,
inescapável. Agora o único portão daquele caminho é um `if` em Python. Um chamador
futuro que esqueça a guarda lê o catálogo do tenant sem o banco reclamar. Está
registrado na SPEC §4 como obrigação de quem escrever o próximo chamador.

### 📌 As três lições de método, e as três são de quem despacha

1. **Espaço de trabalho compartilhado.** Todos os subagentes recebem o mesmo
   scratchpad, e dois escolheram `bin/psql` para o shim — um sobrescreveu o do
   outro **no meio de uma medição**, apontando para o container errado, e o gate
   leu uma cópia do repo 113 linhas atrasada. Quem despacha dá o subdiretório.
2. **Caminho relativo num despacho.** Corrigi a primeira lição escrevendo
   `scratchpad/rev-s5c2/` **sem o caminho absoluto** — e o agente resolveu a
   partir da raiz do repositório, criando 9,3 MB dentro da árvore do projeto.
3. **Ferramenta que redireciona em silêncio.** O wrapper de `psql` desta máquina
   fixa `PGHOST`/`PGPORT` e ignora os exportados. Rodei a suíte três vezes achando
   que era num container meu; era no de dev o tempo todo. Não é destrutivo, mas
   **"rodei isolado" era falso por construção** — e eu havia dito isso ao dono.

As três têm a mesma forma: **o agente faz exatamente o que foi dito, e o que foi
dito não era o que se queria.** Nenhuma foi erro de quem implementa ou mede.

### O que o S5 NÃO fechou, e está declarado

- **Frontend do S5 não despachado** (tela de Unidades e a de rubricas), como em
  S1, S3 e S4.
- ⏳ **`accounting` não cura rubrica.** A §1i nomeia a contabilidade como quem
  confere, e a interseção `admin ∧ compensation` é `{owner, personnel}`. Mudar
  isso é mexer na policy da migration 30 — **item de parada** do `CLAUDE.md`.
  Declarado no docstring e travado por teste.
- ⏳ **`app.payroll_event_map` concede `delete` a `authenticated`** desde a
  migration 30. Inalcançável hoje (o schema `app` está fora dos exposed schemas),
  mas contraria o "não há delete" escrito no módulo. Superfície de outra sprint.
- ⏳ Três `delete` de limpeza **inicial** nas provas vivas não sustentam nada — o
  `raise` já reverte o bloco. Ficam por consistência do argumento que removeu os
  outros 17.

## O frontend do S5 — a tela que o backend tinha construído e ninguém consumia

**Ciclo 1: REPROVADO** (1 ALTO, 2 MÉDIO, 3 BAIXO). **Ciclo 2: REPROVADO**
(2 MÉDIO, 3 BAIXO). **Ciclo 3: APROVADO.** Portões medidos por mim, não
relatados: `vitest` **638** (baseline 545 — +4 arquivos, +93 testes), `pytest`
639, `prettier --check .` limpo, `tsc --noEmit` exit 0, `ruff` limpo.

⛔ **`make db-test` não rodou, e o motivo não é a sprint.** O Docker desta
máquina parou em 12/09 (engine responde 500, integração WSL desligada), e com
ele caem `98`, `99`, o dicionário e o `verificar_docs.py`. `git status` não tem
uma entrada sob `supabase/`: esta metade não tocou migration, policy, view nem
grant. Fica **pendente**, não aprovado.

### 🔴 O ALTO era do despacho, não de quem implementou

A migration `dp_unit_compliance` diz, na seção autorizada pelo dono em 07/09:
*"A tela de Unidades e o link filtrado **leem daqui**; a rota `/dp/laudos` serve
o retorno de `POST`/`renovar` e o `can_write`"*. E concede `select` em
`app.unit_compliance_report` a `authenticated` **só** por causa dessa tela. Meu
despacho mandou ler tudo pela rota e pôs `public.vw_unit_compliance` fora de
escopo: a view ficou **sem consumidor nenhum**, e o grant a `authenticated`
sobrou vivo sem dono.

Não era vazamento — a rota lê a mesma view e o recorte é idêntico. Era
superfície sem dono, decidida em silêncio contra duas declarações escritas.

📌 **E a premissa que sustentava o erro estava no código, em prosa:** o docstring
de `lib/dp/queries.ts` justificava o Caminho 2 dizendo que *"nenhuma das tabelas
desta etapa concede leitura a `authenticated`"* — **falso desde o S5**. É a
terceira aparição da mesma forma nesta etapa: o comentário que virou mentira e
levou o desenho junto. Corrigido; a lista sai da view, `can_write` da rota.

### O que as três revisões acharam, e o padrão que elas desenham

Os três ciclos acharam **o mesmo tipo de defeito em camadas diferentes**: uma
garantia escrita que nada segurava.

1. **Ciclo 1** — a premissa em prosa (acima) e o 500 sem teste: mutar
   `loadComplianceReports` para engolir qualquer erro deixava **617/617 verdes**.
2. **Ciclo 2** — a correção da porta do supervisor podia ser **desfeita** com
   **632/632 verdes**: `layout.test.tsx`, cujo trabalho é exatamente prender qual
   eixo alimenta qual prop, não olhava para a prop nova. E a suíte não fixava
   `TZ`: nesta máquina, em São Paulo, um formatador que **esquecesse** o fuso do
   tenant passava verde — morre só sob `TZ=UTC`, que agora é o do `vitest.config`.
3. **Ciclo 3** — nada novo do mesmo tipo. 14 mutações do revisor, 14 mortas.

📌 **A lição, e ela não é sobre laudos:** *asserção que não existe é indistinguível
de asserção que passa*. As duas sobreviventes do ciclo 2 estavam em arquivos que
se descrevem como a prova daquilo — o teste da fiação e o do fuso. O arquivo
certo existia; a linha não.

### A decisão de papéis, fechada e não omitida

A sidebar oferece Laudos por `COMPLIANCE_REPORT_ROLES` = `HR_ROLES` +
`unit_supervisor` + `regional_manager` + `operations_manager`.

⛔ **A lista é um PROXY, e está escrito no código que é.** `util.can_see_unit`
libera por papel para `{owner, executive, hr, personnel}` **ou** por existir linha
em `app.user_scope` — que qualquer papel pode ter. `/me` devolve papel, não
escopo, então a barra lateral não consegue fazer a pergunta certa. Os três papéis
de operação de unidade entram juntos porque deixar dois de fora repetiria, calado,
o defeito que o terceiro acabou de ter. `accounting` (a porta dele é o Painel de
DP) e `viewer` ficam fora **com teste que prende a ausência**.

⏳ Quando `/me` devolver o escopo resolvido, a pergunta vira *"esta pessoa alcança
alguma unidade?"* e a lista some. É o mesmo item já aberto pelo frontend de S1/S3/S4.

### O que o frontend do S5 NÃO fechou

- ⏳ **`frontend/src/lib/database.types.ts` tem `vw_unit_compliance` inserida à
  mão**, com `Relationships: []`. O bloco saiu do próprio `supabase gen types`
  (contra produção) e o `Row` é correto — o `tsc` o valida de verdade: coluna
  inventada no `select` produz nove `TS2339`. Mas uma geração **local** emitiria
  `unit_compliance_report_unit_id_fkey → vw_unit`, como emite para todas as
  outras views do arquivo. **Consequência para quem regenerar quando o Docker
  voltar: o diff correto NÃO é vazio — é essa entrada aparecendo.** Foi feito à
  mão porque o Docker caiu, e gerar contra produção **regride** o arquivo inteiro
  (produção só expõe `public`, e todas as `Relationships` viram `[]`).
- ⏳ **`GET /dp/laudos` é chamada e tem as `rows` descartadas.** É o preço de a
  view ter o consumidor que a autorizou: a lista vem do Caminho 1, e a rota
  responde só `can_write`. Decisão minha, declarada no docstring.
- ⏳ **O par do guardião não foi medido nesta metade** — *supervisor lê os laudos
  da unidade dele e zero de outra, pela view, como `authenticated`*. A garantia é
  de banco e foi auditada com o backend do S5 em 08/09; o que falta é a medição
  do caminho novo, e ela depende do `db-test` voltar.
- ⏳ Histórico de laudo, `document_id` e filtro de situação na API seguem fora,
  como no despacho.

## Itens próprios abertos pelo S1 — fora do escopo de qualquer sprint desta etapa

**A. 🔴 A matriz dono-do-campo do RH passou a mentir para o cliente.** As
migrations do S1 criaram casa para sete das dez lacunas declaradas em
`backend/operax/rh/ownership.py` (`SEM_COLUNA`): `nivel` diz *"`app.employee_position`
tem só cargo"* e a coluna `level` agora existe; seis `beneficios_*`,
`periculosidade` e `cargo_de_confianca` dizem *"`app.employee_compensation` tem só
`salary`"*, que é exatamente o que `app.employee_benefit` + `app.benefit_type`
resolveram — com os oito códigos da semente batendo um a um.

⛔ **`backend/operax/rh/carga_inicial.py` imprime esse texto para o cliente
durante a implantação.** A reconciliação da matriz é sprint própria; o texto
errado ao cliente é o que não espera por ela.

📌 **E a causa é a terceira aparição do mesmo cego:** `scripts/95_teste_matriz_rh.py`
só recusa nome que esteja em `SEM_COLUNA` **e** na matriz — **nunca reclama de
exceção que sobrou**. É o mesmo defeito do `verificar_docs.py` (que já custou
duas exceções vencidas neste arquivo, corrigidas em 06/09) e do check 4 do `99`.
Três ferramentas de guarda deste repositório suprimem e não reclamam de sobra.

**B. `pg_default_acl` do schema `public` concede `authenticated=arwdDxtm` em
tabelas.** Medido pelo guardião. O que separa isso de um vazamento total é **só o
event trigger que bloqueia `CREATE TABLE` em `public`**. Anterior ao S1 e
permanente — nada desta etapa o introduziu e nada desta etapa o remove.

**C. A metade de frontend do S1 não existe.** `frontend/src/app/dashboard/administracao/`
está na lista `Arquivos` do S1 e o despacho de 06/09 cobriu só o backend.
Registrado para que "S1 fechado" não seja lido como "S1 inteiro".

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
