<!-- verificar-docs: inexistentes-de-proposito app.assistant_metric_scope app.assistant_metric_scope.enabled app.ai_query.prompt_version_id app.ai_query.is_dry_run public.fn_assistant_catalog fn_assistant_catalog app.work_schedule_day -->
<!-- `app.work_schedule_day` entra na lista porque este documento a CITA para
     contar o erro que ela causou na etapa DP. Ela nunca existiu — ver
     `SPEC-DP.md` §0-bis, que registra as três camadas que existem de verdade. -->

# OperaX — sprints da tela de configuração do assistente

Sequência de implementação de `SPEC-AGENTE.md`. Quatro sprints. Cada um tem
**gate verificável**: gate que não fecha = sprint que não terminou, mesmo com o
código escrito.

Esta etapa **não bloqueia nem é bloqueada** pela etapa DP. Não toca nenhuma
tabela dela e o único objeto compartilhado é `app.metric`, em leitura.

---

## A0 — Reconferência antes de escrever qualquer linha

Não é sprint; é o portão. A `SPEC-AGENTE.md` foi escrita contra o snapshot de
**15 migrations** deste diretório e o repositório em andamento tem **37**. Foi
exatamente assim que a etapa DP perdeu um sprint com `app.work_schedule_day`.

Quatro perguntas, respondidas contra o repo em andamento:

1. `app.metric` ainda tem `code` como PK e nenhum `tenant_id`?
2. `metric_read` continua `using (active)`, sem filtro de tenant?
3. `app.ai_query` tem as 13 colunas da SPEC §0.3 e nenhum vínculo a config?
4. `backend/operax/agente/catalogo.py` existe e é quem monta o catálogo?

**Qualquer "não" para aqui e volta para a SPEC.** Um "não" na 1 ou na 2 muda a
§3b inteira; na 4, muda a §4.3.

### ✅ Respondido em 05/09/2026 — quatro de quatro, nenhum "não"

Medido contra o repositório em andamento (37 migrations).

| # | Resposta | Onde |
|---|---|---|
| 1 | ✅ **sim** — `code text primary key`, e **nenhum `tenant_id`**. As colunas são `code · title · description · target_view · dimensions · filters · domain · active` | `09_integracoes_auditoria.sql` |
| 2 | ✅ **sim** — `create policy metric_read on app.metric for select to authenticated using (active)`. Sem filtro de tenant, porque o catálogo é da plataforma | idem |
| 3 | ✅ **sim** — treze exatas: `id · tenant_id · user_id · question · metric_code · parameters · rows_returned · latency_ms · input_tokens · output_tokens · refused · refusal_reason · created_at`. **Nenhuma aponta para configuração** | idem |
| 4 | ✅ **sim** — `backend/operax/agente/catalogo.py` existe e é quem monta: `BINDINGS`, `from_rows`, `reachable`, `describe`, `choose`, `build` | — |

📌 **A 3 confirma o enquadramento do briefing:** a FK nova é conserto, não
feature. `output_tokens` já está lá com o comentário sobre margem negativa, e
sem `prompt_version_id` ela não responde à pergunta para a qual foi escrita —
porque o modelo passa a variar por versão.

---

## A1 — Fundação: camadas, ponteiro, rascunho

### ✅ A0 reconferido em 17/09/2026 — contra 60 migrations, quatro "sim"

A `ai_query` tem **14** colunas agora (`model` entrou depois da SPEC, com a
etapa do assistente ligada) e continua sem vínculo a configuração — não é um
"não". O resto é como em 05/09.

### ✅ Parada aberta pelo dono em 17/09/2026 — e o A1 despachado

As três tabelas em `app` com **exatamente** estas policies:
`assistant_version_read` (select para `authenticated`: `tenant_id is null or
util.has_tenant(tenant_id)`), `assistant_pointer_read` (a mesma) e
`assistant_draft_admin` (for all: `util.is_admin(tenant_id)`, using e with
check). Nenhum papel tem delete; `service_role` só S/I/U. **§7.3 decidida: o
`owner` do tenant edita o rascunho desde o dia 1.** §7.2: sem poda. §7.1 é da
A3/A4.

Duas adaptações à convenção do repo, registradas: o teste de banco vai para
`scripts/97_teste_assistente.sql` ligado em `testar_migrations.sh` (não
existe `tests/db/`); e a v1 da plataforma leva **tokens** no lugar das três
partes dinâmicas de `agente._prompt` (data, catálogo, unidades) — a
fidelidade da transcrição vira teste pytest byte a byte contra a função,
porque só o Python sabe renderizar. `agente.py` **não muda** no A1: o
runtime continua lendo o código; a troca para o ponteiro é de sprint
posterior.

**Entregue em 17/09/2026, em revisão + guardião.** pytest **1229** (+4: a
transcrição da v1 comparada byte a byte com `agente._prompt`, provada
não-tautológica — uma palavra trocada na semente derruba os dois testes),
ruff, suíte de banco OK com **62** migrations, `97_teste_assistente.sql`
**71/71**, `99` item 18, dicionário +111. As duas migrations com o DDL da
§3a como está, as três policies da parada e nenhuma outra (o `do $$` compara
o array de nomes), **nenhum delete para papel nenhum** (append-only por
grant, não só por trigger), e a RPC com as cinco recusas na ordem da SPEC, o
`for update` como primeira instrução e o `grant execute` escrito.

Premissas registradas: os tokens da v1 (`{{hoje}}` = a expressão inteira;
`{{unidades}}` = o bloco inteiro, **inclusive a linha de fallback** — o bloco
é do renderizador); `max_steps` da v1 é **nulo** porque `agente.py` não fixa
teto — semear um número seria escolher, não transcrever; `is_admin` inclui
`hr` e `personnel`, que por isso publicam (a §7.3 fala em "owner"; a policy
prescrita é `is_admin` — aplicado como prescrito).

**Dois achados do próprio implementador, medidos, que viram ciclo 2 por
decisão minha:** (1) **o ponteiro não amarra tenant nem camada à versão** —
o ponteiro de A aceitou `version_id` de B, e um ponteiro de tenant aceitou a
versão de plataforma. Hoje ninguém alcança (o painel não escreve ponteiro; a
RPC aponta só para o que ela mesma criou), mas a A3 ("voltar = mover o
ponteiro") vai receber um `version_id` do cliente. Entra um trigger `before
insert or update` no ponteiro e no `frozen_from_version_id` do rascunho
exigindo `(tenant_id, layer)` da versão iguais aos do escopo — FK composta
não serve (o `tenant_id` nulo da plataforma escapa do `MATCH SIMPLE`). É
mudança no DDL da SPEC, e por isso está escrita aqui. (2) A ordem da SPEC
(`draft_not_found` antes de `not_admin`) deixa o owner de outro tenant
aprender se A tem rascunho — um bit, mas é dado entre tenants: passa a
travar sem checar `found`, checar `is_admin`, e só então `draft_not_found`.

**Guardião de superfície: PASSA**, 12 de 12, zero janelas sujas (a única
divergência de baseline foi este documento, editado por mim depois de o
hash ser tirado — lição: doc de sprint fica fora do baseline dos gates). O
que ele mediu além do relatório: `service_role` **chega no trigger** ao
tentar `update` (tem grant e ignora RLS — quem barra é o trigger, e barra);
`delete` de `service_role`/`authenticated`/`anon` morre no grant; o cascade
de tenant passa com versão **apontada** (a FK foi exercida antes); o md5 do
`content` semeado no banco == o do literal no arquivo da migration == o que
o pytest compara com `agente._prompt`. O item 18 do `99` reprova um `grant
delete` a mais, uma quarta policy e `has_tenant` no lugar de `is_admin` —
não é vácuo.

**Revisão (ciclo 1, mutação no banco do revisor): REPROVADA** — os sete
critérios do gate atendidos, mas um ALTO pela régua da regra 4: o `update`
final do rascunho na RPC leva `where tenant_id = p_tenant_id` e **nenhum
teste o prende** — sem a cláusula, B publicando grava `frozen_from_version_id`
e `updated_by` no rascunho de **A** e a suíte fica verde. Mais três MÉDIOs de
força de teste (`max+1` vs `count+1`, que colide depois de qualquer delete de
versão solta; a ordem das recusas 2–5 pinada só pelo `do $$` da migration;
e a premissa "hoje ninguém alcança" **falsa** para o rascunho — o owner de A
grava `frozen_from_version_id` apontando para versão de B **pela tabela**,
porque a FK ignora RLS). As duas decisões de DDL, medidas: o ponteiro aceita
versão de outro tenant e de outra camada nos dois sentidos; o bit vaza nas
duas direções e ainda distingue tenant inexistente de tenant sem rascunho.
40 mutações, 37 mortas.

**Ciclo 2 despachado em 17/09/2026:** `util.assistant_scope_matches()`
(definer, para a mensagem dizer "escopo diferente" e não "não encontrada")
em `before insert or update` no ponteiro e no `frozen_from_version_id`;
`not_admin` antes de `draft_not_found`, **com a SPEC §3d aberta por mim para
registrar a ordem nova e o porquê**; os pinos do revisor (M9, B11, M6, D3b
como owner pela tabela, `tgenabled` no `99`); `updated_at` do rascunho por
trigger (a A3 vai depender dela); dois comentários que afirmavam o contrário
do que mediam (quem separa `is_admin` de `has_tenant` é o supervisor de A,
não o owner de B). As migrations do A1, não commitadas, são editadas no
lugar.

**Ciclo 2 entregue em 17/09/2026, em revisão + guardião de novo.** O
implementador foi além do despacho num ponto, e mediu antes: com o helper de
escopo em `invoker`, o D3b (owner de A apontando o rascunho para a v1 de B
pela tabela) **passava em silêncio** — a RLS esconde a versão de B do trigger,
o trigger devolve `new`, e a FK, que ignora RLS, aceita. Então o helper é
`definer` e versão que ele não encontra também levanta, nunca cai para a FK.
Sem policy a mais ou a menos: a parada continua sendo as três. `97` foi de 71
para 95 asserções (bloco 8 com os cruzamentos como postgres; D3b como owner
pela tabela; `not_admin` para tenant inexistente e para tenant sem rascunho;
B11 com delete real da versão solta; M9 conferindo o rascunho de A depois de
B publicar; `updated_at` por trigger). Suíte inteira verde no scratchpad do
implementador (62 migrations, `verificar_docs` ✅), pytest 1229. Baselines de
checksum refeitos **sem** `docs/SPRINTS-AGENTE.md` — lição do ciclo 1.

**Revisão (ciclo 2): APROVADA.** O ALTO e os três MÉDIOs caíram cada um em
asserção própria do `97` e, onde é estrutural, no `99`: M9 isolado (trigger
de escopo desligado na cópia, `97` sem 8d/8h) cai em "a publicação de B não
tocou o rascunho de A" e o controle com a RPC original passa por ela — a
asserção mede o M9, não o trigger. D1/D2/D2b/D3 recusados como postgres;
D3b recusado **como owner de A pela tabela** com "outro escopo" (e o owner
não enxerga a versão de B: a mensagem vem do definer, não da FK); uuid
inexistente recusado pelo trigger, nunca entregue à FK. Owner de B contra A
sem rascunho, com rascunho e contra tenant inexistente: `not_admin` nos
três. Dezesseis mutações, quinze mortas — a sobrevivente (helper sem checar
`layer`) é equivalente por construção, porque as constraints
`*_scope_coerente` já amarram `layer` a `tenant_id`. Os 71 rótulos do ciclo
1 estão nos 95 com os mesmos valores esperados. Quarta sobra do falso verde,
BAIXO e do repositório: `updated_by` do rascunho é livre para o admin
(spoof de autoria, não cruzamento de tenant) — o mesmo vale para as outras
onze tabelas de `app` com `*_by` gravável por `authenticated`. BAIXOs
restantes: o `else` do helper trata qualquer tabela desconhecida como
rascunho (fechado por mim antes do commit, com `raise`); §3a da SPEC sem os
triggers (fica para quando a SPEC abrir).

**Guardião (ciclo 2): PASSA.** Suíte inteira no `operax_test` (62 migrations,
`97` 95/95, `98`, `99` item 18, dicionário igual ao da árvore byte a byte,
`verificar_docs` ✅), 16 janelas de checksum limpas. Superfície: o helper
`util.assistant_scope_matches` não é executável por `anon`, `authenticated`
nem `service_role` (só o dono do banco, e só como trigger); `public` ganhou
uma função só (`fn_publish_assistant_prompt`), nenhuma view depende das três
tabelas; as policies são exatamente as três da parada; ninguém apaga. Cenário
próprio com um segredo plantado no rascunho de B: nenhuma mensagem do
trigger ou da RPC carrega conteúdo, `tenant_id` ou id de versão de B — só o
uuid que o próprio chamador passou. Observação registrada, não reprova:
"outro escopo" ≠ "não existe" revela um bit de existência sobre um uuid v4
não enumerável, preço declarado de o teste distinguir definer de invoker.
Reaplicação dupla das duas migrations = estado idêntico ao rebuild limpo
(snapshot de 42 linhas do catálogo).

### ✅ A1 fechado no código em 17/09/2026

Dois ciclos. O que entrou: `20260917181556_assistant_prompt_layers` (três
tabelas em `app` com RLS e exatamente as três policies da parada; versão
imutável por trigger `before update`; escopo amarrado à versão por
`util.assistant_scope_matches()`, definer, nos dois lugares em que uma linha
aponta para versão; `trg_updated_at` no rascunho; plataforma v1 semeada com
o texto que estava no ar — transcrito, não reescrito, e o pytest compara o
literal da migration com `agente._prompt` byte a byte) e
`20260917181559_assistant_publish_fn` (`public.fn_publish_assistant_prompt`,
definer, `for update` primeiro, `not_admin` antes de aprender qualquer coisa,
cinco recusas nomeadas, `max + 1`). `scripts/97_teste_assistente.sql` com 95
asserções, ligado na suíte; `99` item 18; `test_agente_prompt_seed.py`.
Gates no fechamento: pytest 1229, ruff limpo, suíte de banco RC=0 com o
`raise` do helper para tabela desconhecida (o BAIXO do revisor, fechado
antes do commit).

O que **não** está em produção: as duas migrations do A1 entram na fila das
sete que o classificador segurou (5 do C3, 2 do C5) — são **nove** agora,
todas na mão do dono. O runtime **ainda não lê** a camada de versão: o
`agente.py` continua montando o prompt do código, e é assim de propósito —
a troca acontece na A3/A4, quando houver tela para publicar e Execuções para
mostrar qual versão produziu. Até lá a v1 semeada é o retrato, e é igual ao
que roda.

Dívidas nomeadas: SPEC §3a mostra o DDL sem os três triggers (abrir a SPEC
quando A3 a abrir); `updated_by` gravável pelo admin em doze tabelas de
`app` (padrão do repositório, spoof de autoria, não cruzamento); concorrência
real da RPC não exercida (só a posição textual do `for update`); poda §7.2
fora; decisão do dono pendente sobre `is_owner` vs `is_admin` para editar e
publicar (hoje hr e personnel também podem).

**Parada da A2 aberta pelo dono em 17/09/2026**, antes de a A1 fechar, para
não parar entre as duas: `app.assistant_metric_scope` com leitura por
`util.has_tenant` (o runtime lê como o usuário) e insert/update por
`util.is_admin`, sem delete (reabilitar = `enabled = true`); e
`fn_assistant_catalog` devolvendo também `target_view/dimensions/filters`,
que o runtime precisa e a SPEC não listou. Despacho da A2 sai quando o
ciclo 2 da A1 commitar — as duas tocam `99`, `testar_migrations.sh` e o
dicionário.

**Por que primeiro:** tudo depende do modelo de versão. E é o único sprint que
mexe em estrutura de segurança — isolado, é revisável em uma sentada.

- Migrations `assistant_prompt_layers` e `assistant_publish_fn`.
- Semente da camada `platform` v1 com o prompt que hoje vive em código.
  **Transcrever, não reescrever.** Se o texto melhorar no caminho, a primeira
  versão deixa de ser o retrato do que estava no ar, e o histórico começa
  mentindo. Melhoria é a v2, com autor e data.
- `public.fn_publish_assistant_prompt` com as cinco validações e o `for update`
  no rascunho.
- Transcrever as sete verificações da SPEC §3a para
  `scripts/97_teste_assistente.sql`.

⛔ **Parada obrigatória antes de aplicar:** três tabelas novas em `app` com
policy de RLS.

**Gate:**

- as sete linhas da tabela da SPEC §3a passam como teste, **incluindo a 7** (o
  cascade de `app.tenant` leva versão e ponteiro e não trava na FK);
- publicar duas vezes o mesmo texto devolve `draft_unchanged` e **não** cria
  versão;
- publicar sem ponteiro de plataforma devolve `platform_layer_missing`;
- um `owner` de outro tenant chamando a RPC recebe `not_admin` — e o teste
  chama **a RPC**, não a policy: a função é `security definer` e não herda RLS,
  então é a única checagem que importa;
- `grant execute` para `authenticated` está **escrito** na migration.
  `trg_lock_down_new_function` não cobre `public`; sem a linha, a RPC nasce
  inacessível e o sintoma é 403 sem nada no log.

## A2 — Capacidades

**Por que separado:** é a única parte que o cliente opera sozinho, e a única com
uma invariante que precisa sobreviver a toda mudança futura (SPEC §4.1).

- Migration `assistant_metric_scope` (ausência = habilitada).
- `public.fn_assistant_catalog` — os três filtros numa resposta.
- `catalogo.py` passa a **chamar a RPC** em vez de montar catálogo por query
  própria.

**Despachada em 17/09/2026, sobre o A1 commitado (`9bf565e`).** Duas
decisões minhas no despacho, além do que a parada fixou: a RPC é **`security
invoker`** — as três réguas da §4.2 já são objetos que o usuário alcança
(`metric_read`, a policy de leitura nova, `util.can_see_domain`), e definer
aqui seria privilégio sem necessidade; e **quem não é membro do
`p_tenant_id` recebe zero linhas**, não erro, porque a RPC é Caminho 1 e o
cliente escolhe o parâmetro. As três policies por nome:
`assistant_scope_read` (select, `has_tenant`), `assistant_scope_insert` e
`assistant_scope_update` (`is_admin`) — sem `for all`, que cobriria delete.
`reachable()`/`domains()` ficam no `agente.py` (fora do escopo; `choose`
ainda usa `domains` para a recusa nomeada `sem_dominio`), e a redundância
fica registrada como dívida. Gate 2 vira teste de texto sobre `executor.py`
e `catalogo.py`: `from app.metric` reprova, `fn_assistant_catalog` ausente
reprova.

**Entregue em 17/09/2026, em revisão + guardião.** `20260917203425_assistant_metric_scope`
e `20260917203429_assistant_catalog_fn` (RPC `language sql stable security
invoker`, medida como `authenticated` antes dos testes: owner A vê 11
métricas, `documents_expiring` de pii não visível; supervisor lê o escopo e
vê `daily_trend`; owner B chamando A recebe zero). `executor._CATALOG_SQL`
passa a `from public.fn_assistant_catalog(%(tenant_id)s) where visible_to_me`;
`Metric` **não** ganhou campo (tudo o que chega ao `from_rows` já é visível;
as duas colunas são da aba). `97` ganhou a seção A2 (41 asserções, 136 no
total, contador no cabeçalho); `99` item 19; `test_agente_catalogo_rpc.py`
com o gate 2 como teste de texto (distingue docstring de string de SQL por
`ast`). Seis mutações do próprio implementador, todas mortas — a m5 em duas
variantes, porque uma prova a checagem por nome e a outra por `cmd`. pytest
1235, suíte 64 migrations RC=0. Achado dele que vira dívida nomeada: a
segunda régua que ficou (`reachable`/`domains`) já tem um caso latente —
`_PERMISSIONS_SQL` pergunta quatro domínios e o enum tem cinco desde
`banking`; uma métrica futura `banking` viria visível pela RPC e seria
descartada por `reachable`. Disponibilidade, não vazamento; nenhuma métrica
é `banking` hoje.

**Guardião: PASSA, seis de seis.** Suíte inteira no `operax_test` (64
migrations, `97` 136, `98` 293, `99` 1–19, dicionário byte a byte igual ao
da árvore, `verificar_docs` ✅ com o marcador do SPEC sem os dois objetos),
doze checkpoints de hash limpos. Superfície: o diff de catálogo entre 62 e
64 migrations é só o que a A2 cria — uma função em `public` (invoker,
`search_path`, anon **f**), três policies, uma tabela em `app`; nenhuma
view nova, nenhuma dependente da tabela; exposed schemas do ensaio
inalterados. Matriz `visible_to_me` medida por seis pessoas como
`authenticated` e cruzada independentemente com `domain_permission` ×
`tenant_member`: dez de dez, zero violação; membro de A recebe 0 linhas de
B e vice-versa; nove chaves no JSON, nenhum `tenant_id`/`updated_by`;
métrica inativa com escopo `enabled = true` não devolve `target_view`.
`delete` recusado por grant para owner, supervisor **e `service_role`**.
Item 19 não-vácuo em cinco mutações. Observação registrada: a guarda de
corpo do item 19 é textual (`like '%has_tenant%'`) — tirar o `has_tenant`
do `where` e deixá-lo em comentário passa no `99` e cai no `97` (A2-e2).
A suíte inteira é a régua; o `99` sozinho não é.

**Revisão: REPROVADA por força de teste — código correto em tudo o que
mediu.** 31 mutações. Um ALTO pela régua literal do despacho: o gate da §4.3
passava verde com o catálogo vindo de `app.metric` — `"from app." +
"metric"` e `from app . metric` escapavam do gate textual, um módulo novo
lendo `app.metric` também, e as três asserções de runtime casavam substring
no texto cru, então `-- from public.fn_assistant_catalog(…) where
visible_to_me` num **comentário SQL** as satisfazia (21/21 verdes com a
desabilitada chegando ao modelo, medido no Postgres); `where visible_to_me
= false` e `is not null` também passavam. Um MÉDIO: o `left join` sem
`s.tenant_id = p_tenant_id` sobrevivia a `97`, `99` e ao `do $$` — e não é
equivalente: usuário membro de A **e** B, com B desligando o que A não
desligou, recebe 12 linhas em vez de 11, `daily_trend` desligada por B e
`payroll_summary` duas vezes, uma habilitada. BAIXOs: `A2-h1` aceitava
qualquer `permission denied` (com grant a anon, a recusa vinha de
`app.metric`); `where m.active` equivalente sob invoker (a RLS filtra) mas
não sob definer; `grant execute … to service_role` é morto (`service_role`
não tem select em `app.metric`); `order by` sobrevive e não importa. Falso
verde acrescentado por ele: `coalesce(null, true)` converte "não pode ler o
escopo" em "habilitada" — qualquer estreitamento futuro de
`assistant_scope_read` abaixo do `has_tenant` do corpo faz a desligada
**reaparecer** sem erro; `A2-0b`/`b5` e o `99` prendem a policy igual à
condição do corpo.

**Fechado por mim antes do commit, cada um provado na cópia:** o teste
Python tira comentários SQL antes de casar, exige que a instrução executada
**termine** em `where visible_to_me` e não contenha `app.metric` com
qualquer espaçamento, junta os literais adjacentes antes de procurar, e o
gate textual varre **todos** os módulos de `operax/` e `server/` (77
arquivos parametrizados) — b4b cai em três asserções, b9/b10/b7a em uma
cada, controle 83 verdes. `97` ganhou o bloco (j): quarto usuário, membro
de A e de B, B desliga `daily_trend` e grava `payroll_summary`; cinco
asserções (141 no total) — r2 cai em `A2-j2`. `99` item 19 cobra
`s.tenant_id = p_tenant_id` e `m.active` no corpo — r2 e r1 caem nele.
`A2-h1` exige `permission denied for function` — r6 cai "pelo motivo
errado". O grant morto a `service_role` fica registrado como dívida, não
retirado: o padrão das RPCs recentes o tem, e retirá-lo é decisão de
padrão, não desta sprint.

### ✅ A2 fechado no código em 17/09/2026

Um ciclo de implementação e um de conserto meu. O que entrou:
`20260917203425_assistant_metric_scope` (tabela em `app`, ausência =
habilitada, três policies por nome, nenhum delete para papel nenhum,
`trg_updated_at`) e `20260917203429_assistant_catalog_fn`
(`public.fn_assistant_catalog`, `security invoker`, nove colunas, zero
linhas para não-membro); `executor.load_catalog` lendo a RPC com `where
visible_to_me` no SQL e nada de `app.metric` em módulo nenhum do backend
(gate de texto sobre 77 arquivos + asserção sobre a instrução executada sem
comentários); `97` com 141 asserções (46 da A2, inclusive o usuário em
dois tenants); `99` item 19. Gates no fechamento: pytest 1312, ruff limpo,
suíte de banco 64 migrations RC=0.

Os dois gates da sprint, como pedidos: (1) desabilitar `payroll_summary`
tira a métrica do catálogo do owner e do supervisor; reabilitar devolve ao
owner e **não** ao supervisor, que continua sem `compensation` — medido
como `authenticated` pelo implementador, pelo revisor e pelo guardião, e
no alvo: com escopo `enabled = true` explícito o supervisor recebe
`visible_to_me = false` **e** zero linhas de `vw_payroll_summary`. (2) O
teste que falha se o runtime montar catálogo por conta própria, endurecido
até o revisor não conseguir burlá-lo sem mudar o comportamento.

O que **não** está em produção: as duas migrations entram na fila do dono —
**onze** agora (5 C3, 2 C5, 2 A1, 2 A2). O runtime já lê a régua única em
produção assim que a API subir com este commit — **e é por isso que a
ordem importa**: o `executor.py` novo chama `public.fn_assistant_catalog`,
que não existe lá; sem as migrations da A2 aplicadas, **o assistente inteiro
responde "Não consegui carregar as métricas agora"** em produção. Push
deste commit e aplicação das duas migrations têm de acontecer na mesma
janela, migrations primeiro.

Dívidas nomeadas: `reachable()`/`domains()` no `agente.py` são uma segunda
régua que só esconde (quatro domínios de cinco; uma métrica `banking`
futura viria visível pela RPC e seria descartada) — remover na A3/A4;
`grant execute … to service_role` morto na RPC (sem select em
`app.metric`); `_CATALOG_SQL` nunca roda contra o Postgres em gate nenhum
(o `91` não importa o executor porque ele traz o driver); `app.metric.domain`
é declarado, não derivado do alvo — quem semeia métrica com domínio errado
vaza existência, não dado; lista de RPCs do Caminho 1 no `CLAUDE.md`
defasada (pré-existente).

**Gate — dois testes, e o segundo é o que importa:**

1. desabilitar `payroll_summary` faz o assistente responder "não tenho esse
   dado" para uma pergunta de folha, e **habilitar de volta não concede nada a
   um papel sem `compensation`** — continua recusando, agora por domínio. É a
   invariante da §4.1 virada em teste: a tela só estreita.
2. um teste que **falha se `catalogo.py` montar o catálogo sem a RPC** — busca
   por `from app.metric` / `.from("metric")` no módulo. É a régua única da
   §4.3, e é a defesa contra o defeito que o DeskcommCRM pagou para descobrir:
   tela e runtime com réguas próprias divergem só no caso raro, que é onde
   ninguém olha.

## A3 — Telas: configuração, histórico, teste

- Aba **Configuração**: camada `platform` em leitura, camada do tenant editável,
  contador de caracteres contra o limite.
- ⛔ Quando `frozen_from_version_id` do rascunho ≠ versão apontada, a tela mostra
  **as duas** e diz qual o botão substitui (SPEC §2). Esconder uma é o defeito.
- Aba **Histórico**: versões, autor, data, diff, e voltar (move o ponteiro).
- Aba **Teste**: roda de verdade, grava `is_dry_run = true`.
- ⛔ A aba de teste diz, em texto fixo: *"O teste consulta dados reais, com as
  suas permissões."*
- ⛔ **Nenhum seletor de papel na aba de teste.** "Como ficaria para um
  supervisor" se responde listando as métricas que ele alcança — nunca
  executando como ele.

**Onda backend despachada em 17/09/2026, sobre a A2 commitada (`88b7c4d`).**
Duas coisas mudaram no plano, e o porquê: a migration §3c
(`assistant_run_link`) **sobe da A4 para cá**, porque a aba Teste grava
`is_dry_run` e não há como testar sem a coluna; e a **SPEC §7.1 foi decidida
pelo dono em 17/09/2026: terceira via**, `draft_content_hash` em
`app.ai_query` — o teste de rascunho fica rastreável sem virar versão.
Decisões minhas no despacho: `prompt_version_id` = a versão de tenant no
ar, senão a de plataforma (nulo continua sendo "antes do versionamento");
o texto em código **sai** e não há fallback — sem ponteiro de plataforma o
turno emite `error` e não grava (em produção é a ordem migrations → push,
já registrada); escrita pelo padrão de `canais.py` (`is_admin` como o
usuário, gravação + `audit_log` sob `service_role`), não pela policy da
tabela; publicar chama a RPC como o usuário e mapeia os cinco `P0001`;
rollback **não** é RPC nova — 404 antes de qualquer escrita, `update` do
ponteiro sob `service_role`, o trigger de escopo como rede; o teste roda
sempre como quem chamou. A onda 2 (as quatro abas) é escrita a partir do
contrato que esta onda deixar em `models.py`.

**Onda backend entregue em 17/09/2026, em revisão + guardião.** Migration
`20260918001032_assistant_run_link` (três colunas em `app.ai_query`, duas
checks nomeadas, índice parcial, FK sem cascade, policies pinadas em
`{ai_query_read}`); `operax/agente/prompt.py` (`load_layers` sob
`user_scope`, `render` puro, token desconhecido → erro de configuração);
`agente._prompt` **saiu** — o pino da v1 virou a fixture
`tests/fixtures/prompt_v1_rendered.txt`, gerada pelo `_prompt` antigo antes
de apagá-lo e sem gerador no repositório de propósito; `build_model` usa
provider/model da plataforma como default pela mesma allowlist, e modelo
que a instalação não roda é **503**, nunca outro modelo em silêncio;
`max_steps` medido no LangGraph (`recursion_limit = 2·max_steps + 2`, tabela
k×limite no relatório); oito rotas em `/assistente/configuracao/*` no padrão
de `canais.py`; `/testar` reusa o SSE de `/perguntar`. pytest 1383
(+71), `97` 164 asserções (+23 da A3), 65 migrations RC=0. Oito mutações
mortas — a m1 (`registrar` sem `prompt_version_id`) sobreviveu ao primeiro
ciclo dele e ganhou o teste que a mata.

⚠️ **Risco de produção que ele apontou e eu não consigo medir sem expor
segredo:** a v1 semeada pede `openai/gpt-5.4-mini`; se o `operax-api` no
Railway **não** tiver `OPENAI_API_KEY` (só nomes importam), o assistente
responde 503 depois deste commit até uma v2 por migration ou a chave
entrar. Conferir no painel antes do push. Modo de falha do push antes das
cinco migrations do agente, agora nomeado: `load_layers` → 500 antes do
primeiro byte, e `registrar` falhando sob o `suppress` do `finally` →
**turno pago sem linha** em `ai_query`.

**Guardião (onda backend): PASSA, sete de sete.** Suíte no `operax_test`
(65 migrations, `97` 164, `98`, `99` 1–19, dicionário byte a byte,
`verificar_docs` ✅), treze checkpoints de hash limpos. Diff de catálogo
64→65 = **dez linhas, todas em `app.ai_query`**; `public` 9 relações → 9,
15 funções → 15; `pg_policies` 105 → 105 (o "115" do dicionário é
artefato de contagem por linha, policy com `qual` multilinha conta duas
vezes — não é da A3); grants 568 → 568; nenhuma view expõe as três
colunas. API medida **com a app real e o banco real** (`TestClient` +
`operax_test`, RLS de verdade, modelo falso): 91 checagens, zero falhas —
supervisor recebe `draft = null` e nunca o texto, quatro 403 sem vazar o
rascunho, cinco streams capturados inteiros sem hash, sem
`prompt_version_id`, sem texto de camada, a única uuid é o `consulta_id`;
e o não-vácuo: no banco os dois testes com rascunho têm `is_dry_run`,
`sha256` e versão de plataforma. Como `service_role`, ponteiro de A para
versão de B cai no trigger da A1. Fato registrado, não achado:
`tenant_scope` roda como o dono de `DATABASE_URL` (`postgres`, bypassrls),
não como o role `service_role` do Supabase, que nem tem insert em
`ai_query`. Não-vácuo do `do $$` em quatro mutações; reaplicação ×2 idêntica.

**Revisão (onda backend): REPROVADA por um único MÉDIO de força de teste;
os outros onze critérios medidos e OK.** Os quatro SQLs que decidem qual
texto de tenant entra no prompt e na tela (`_LAYERS_SQL`, `_ON_AIR_SQL`,
`_DRAFT_SQL`, `_VERSIONS_SQL`) não tinham teste que caísse quando
`tenant_id = %(tenant_id)s` some — os testes conferiam só os parâmetros,
que continuam iguais com o SQL mutado. Não é vazamento: ele mediu no
banco real que a RLS é a rede (contexto forjado de usuário de B com
`tenant_id` de A recebe só plataforma e rascunho nulo) e que `deps.py` não
deixa o `tenant_id` vir do cliente; mas "cruzamento de tenant no prompt sem
quem prove" é MÉDIO pela régua. O resto: `_require_admin` antes de todo
`tenant_scope` (quatro rotas, 403 com a transação nunca aberta, e no banco
real também para contexto forjado); rollback 404 antes de escrever e, como
`postgres`, ponteiro de A → versão de B recusado pelo trigger da A1; a
fixture da v1 é **byte a byte** o `_prompt` do HEAD `88b7c4d` (sha256
`402fd7aa…`), inclusive sem unidades e com um terceiro conjunto de
entradas; `build_model` com só Anthropic configurada e plataforma pedindo
OpenAI → 503, nunca outro modelo; `max_steps` reproduzido
(`2k + 2`); sem plataforma → `error` e **zero** linhas em `ai_query`, no
banco real. 27 mutações, 22 mortas, 4 sobreviventes = o MÉDIO, 1 (x2)
equivalente para estado alcançável. BAIXOs: `{{ hoje }}` com espaços fica
literal sem erro (a aba Teste mostra); SPEC §5 contradizia a §7.1
(**fechado por mim**); `/testar?use_draft` faz `is_admin` antes do
limitador (custo pago continua atrás dele). Nono falso verde, dele:
`service_role` não tem insert em `ai_query` — quem grava é o dono de
`DATABASE_URL`; quem endurecer grants precisa saber.

**Fechado por mim antes do commit:** quatro asserções de texto — o
predicado `tenant_id = %(tenant_id)s and layer = 'tenant'` nas três
leituras de ponteiro/versão e `where tenant_id = %(tenant_id)s` no
rascunho — provadas na cópia: r2, r2b, r2c e r2d caem em um teste cada,
controle 51 verdes.

### ✅ A3 — onda backend fechada no código em 18/09/2026

O que entrou: `20260918001032_assistant_run_link` (`app.ai_query` com
`prompt_version_id` sem cascade, `is_dry_run`, `draft_content_hash` com
duas checks, índice parcial, policies pinadas); `operax/agente/prompt.py`;
`agente._prompt` removido e a v1 pinada por fixture; `build_model` com o
default vindo da plataforma pela mesma allowlist; `max_steps` como
`recursion_limit = 2·max_steps + 2`; oito rotas em
`/assistente/configuracao/*`; `/testar` reusando o SSE de `/perguntar`;
`97` com 164 asserções; pytest 1383. Gates de fechamento: suíte 65
migrations RC=0, ruff limpo.

O que muda em produção com este commit, e a ordem: o runtime passa a ler o
prompt do banco. Sem as **cinco** migrations do agente (2 A1, 2 A2, esta)
aplicadas antes do push, o assistente inteiro cai — 500 antes do primeiro
byte, e turno pago sem linha em `ai_query`. Com elas, o texto que roda é a
v1 semeada, igual ao que rodava. E a chave: a v1 pede `openai/gpt-5.4-mini`;
sem `OPENAI_API_KEY` no `operax-api`, 503. Fila de migrations na mão do
dono: **doze**.

Dívidas nomeadas: `{{ hoje }}` com espaços fica literal (a aba Teste
mostra); `/testar?use_draft` checa admin antes do limitador; turno que
morre no teto de passos é gravado com `error` genérico, indistinguível de
"provider caiu" (A4 pode querer distinguir); "qual versão de tenant estava
no ar quando o rascunho foi testado" não é recuperável da linha — só o
hash; `publicar` grava a trilha numa segunda transação (janela estreita
de "publicado sem audit"); `reachable()`/`domains()` da A2 seguem.

**Onda 2 (as quatro abas) despachada em 18/09/2026, sobre `e2195c5`.**
Página em `/dashboard/administracao/assistente` com a porta `isAdmin` de
Conexões (404 para quem não é); aba na query string; tipos espelhando
`models.py` campo a campo; SSE pelo cliente de `stream.ts` com o endpoint
parametrizado, sem duplicar o parser; diff de versões por LCS de linhas
sem dependência nova. Os dois gates da sprint viram testes de tela: o
aviso da SPEC §2 com as duas caixas visíveis, e a frase fixa de dados
reais mais a **ausência** de seletor de papel.

**Onda 2 entregue em 20/09/2026, em revisão.** Quatro abas em
`/dashboard/administracao/assistente`, porta `isAdmin` com `notFound()`
antes de qualquer leitura, aba pela query string, cada aba lendo só o que
usa. O transporte do SSE virou um lugar só (`streamAssistant(path, body,
…)`, com `askAssistant` de três linhas por cima) e a renderização de
evento é a mesma da conversa — a aba Teste não ganhou uma segunda cópia
que divergisse. +95 testes (1048 no total), `tsc`, `prettier`, `lint` (os
mesmos três warnings de antes, nenhum em arquivo novo) e `build` verdes.
Seis mutações, seis mortas.

Decisão dele que eu endosso: **Publicar não salva sozinho.** O botão
compara a caixa com o que foi salvo e, se diferirem, pede para salvar
**sem chamar a API** — encadear transformaria uma edição que a pessoa só
queria guardar no texto que passa a governar o assistente. O
`draft_not_found` do backend continua mapeado para a mesma frase: é a
rede, não o caminho.

**Dois falsos verdes que ele não podia fechar da tela, e que são de
contrato:** (1) `POST /publicar` congela o que estiver em
`app.assistant_draft` no instante da chamada, sem receber nada que
identifique o rascunho que a tela viu — dois admins no mesmo minuto e um
publica o texto do outro, sem que o backend possa recusar
(`draft_unchanged` compara com a versão no ar, nunca com o que a tela
mostrava). Proposta: aceitar o `updated_at`/hash do rascunho lido e
responder 409 `draft_moved`. (2) O selo "Rascunho" de cada turno de teste
vem do `use_draft` que a tela enviou, não do que o servidor rodou — hoje
seguro só porque `/testar?use_draft` sem rascunho é 404 antes do stream;
no dia em que virar fallback, a tela mente. Proposta: `done` carregar
`prompt_version_id` e `draft_content_hash`. Terceiro, menor: `versions =
null` degrada a **frase** do aviso da §2, nunca o aviso nem as duas
caixas (o gate 1 prende isso); `frozen_from_version_number` em
`PromptScreen` mataria a segunda chamada.

**Revisão (onda 2): REPROVADA por um mutante que sobrevive aos 1048
testes.** `use_draft` preso em `true` passava verde — e o efeito é o
defeito da §2 na aba que existe para dizer qual texto governou: quem **não**
marca a caixa recebe a resposta do rascunho com o selo dizendo "Versão no
ar". Os dois testes se cruzavam sem se cobrir (um exercita só o `true`; o
outro afirma a chamada, mas com a função mockada, então o corpo nunca era
observado). O 404 do backend não alcança isso — ele cobre a metade de trás;
a da frente é a intenção chegar fiel ao corpo. Mais um MÉDIO: `hasDraft`
colapsava "li e não há" com "**não consegui ler**" (401, 403 e o 503 de
"sem plataforma publicada"), e a tela **afirmava** *"Não há rascunho
salvo"* — comportamento seguro, frase falsa, e é a única coisa que o admin
lê. Dos outros dezesseis mutantes, todos mortos: o `<datalist>` de redação
neutra foi pego pelo `role`, não pelo texto; a região nomeada do painel de
teste falha **alto** (`getByRole` lança) nos dois ataques à âncora; e a
caixa do texto no ar dobrada dentro de um `<details>` — que continua no DOM
— cai porque a asserção é `toBeVisible`, não `toBeInTheDocument`.

**Fechado por mim antes do commit:** a asserção do caso negativo de
`use_draft`, e `hasDraft: boolean | null` com a frase que diz que não foi
possível saber. Provados na cópia: M15 e o colapso caem um teste cada,
controle 50 verdes. BAIXOs registrados: as duas leituras do aviso não são
do mesmo instante (segunda razão para `frozen_from_version_number` em
`PromptScreen`); `aria-checked` redundante; nenhum turno usa `AbortSignal`
(dívida herdada da conversa). E um achado que não é desta onda: se o tipo
de `draft_ahead_of_air` for afrouxado para opcional, o aviso inteiro some
em silêncio e a suíte fica verde — hoje quem segura é o `tsc`, porque
resposta de API não tem validação de runtime em lugar nenhum do frontend.

### ✅ A3 fechada no código em 20/09/2026 — as duas ondas

Backend em `e2195c5`; a tela nesta. Os dois gates da sprint viraram teste e
foram mutados: o aviso da SPEC §2 com **as duas caixas visíveis ao mesmo
tempo** (cinco mutações, inclusive dobrar a caixa num `<details>` sem tirá-la
do DOM), e a frase fixa de dados reais mais a **ausência** de seletor de
papel (cinco, inclusive um `<input list>` de redação neutra, pego pelo
`role`). Gates: 1050 testes, `tsc`, `prettier`, lint 0 erros, build compila.

O que falta para a etapa fechar de verdade é a A4 — e o que ela precisa
carregar já está medido: as duas dívidas de contrato desta onda
(`draft_moved` na publicação; `prompt_version_id`/`draft_content_hash` no
`done`) entram no despacho dela, porque a rota ainda não subiu e as duas
tocam o mesmo router.

**Gate:** rollback para a v1 com rascunho na v3 mostra as duas versões na tela;
um teste de tela cobra a frase de dados reais e a **ausência** de seletor de
papel — a ausência é testável e some sem aviso se não for.

## A4 — Execuções

- Migration `assistant_run_link` (`prompt_version_id`, `is_dry_run`, índice
  parcial).
- Aba **Execuções**: pergunta, métrica escolhida, linhas, latência, tokens,
  recusa com motivo, versão que produziu.

**Despachada em 20/09/2026, sobre `9487358`.** A migration §3c já entrou na
A3, então a A4 são três coisas: as duas dívidas de contrato da A3
(`draft_moved` como **sexta** recusa, entre `draft_not_found` e
`draft_empty`, com `p_seen_updated_at` nulo = comportamento de hoje; e o
`done` carregando `prompt_version_id` e `draft_content_hash`, que é a
única edição autorizada no `CLAUDE.md`), mais as duas funções da tela:
`fn_assistant_runs` e `fn_assistant_cost_by_version`, as duas **invoker**
— a RLS de `ai_query` é `own or is_admin`, e herdar isso é o desenho, não
um filtro de papel no corpo. `version_label` é texto pronto e diz **"antes
do versionamento"** quando o id é nulo; "v1" ali seria inventar
procedência, que é o erro que esta etapa existe para não cometer.

**Gate:** custo por competência **quebrado por versão de prompt** — é o que as
colunas de token existiam para responder e não respondiam (SPEC §0.3). Dry-run
fora de toda média. Linha anterior ao versionamento aparece como "antes do
versionamento", **nunca** atribuída à v1: atribuir seria inventar procedência,
que é o erro que esta etapa inteira existe para não cometer.

---

## Ordem

```
A0 ── A1 ──┬── A3 ── A4
           │
           └── A2
```

A2 e A3 são paralelos por pessoas diferentes: um é backend + banco, o outro é
tela. A4 depende de A3 só porque a aba mora no mesmo arquivo de abas.

## O que fecha a etapa

Uma mudança de prompt **publicada pelo painel**, em produção, sem deploy — e a
execução seguinte aparecendo em Execuções com a versão nova ao lado. É o ciclo
inteiro num movimento só, e é a única prova de que as quatro partes se
encaixam.

## O que fica fora, com o destrave nomeado

- **Agente autônomo em WhatsApp** (SPEC §6.1) — não é "depois", é outro
  produto, e o caminho para ele passa por derrubar a regra 11 de propósito.
- **Credencial e orçamento por tenant** (§6.2, §6.3) — enquanto a EURECA pagar
  o modelo.
- **Flywheel de propostas** (§6.4) — destrava quando existir rotulagem de
  recusa, nem que seja manual e de 200 linhas.
- **Papel de plataforma** (§1) — a camada `platform` é semeada por migration.
