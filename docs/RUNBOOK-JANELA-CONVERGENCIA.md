<!-- verificar-docs: inexistentes-de-proposito app.job_execucao app.sync_execucao app.integracao -->

# Runbook — janela de convergência

**Substitui a "Fase 3 — janela" de `PLANO-RECONCILIACAO-NUVEM.md`**, que ficou
desatualizada em dois pontos que mudam a operação inteira:

| | Fase 3, como escrita | Hoje |
|---|---|---|
| Migrations a aplicar | **5** (11b, 12–15) | **18** (11b, 12–28), mais a limpeza do passo 2a |
| Teto de parada | **48 h**, imposto pelo código | **48 h ainda**, agora medido no runner da Vercel — ver §5 |
| Natureza da janela | rename | **release de convergência**: schema + Edge Functions + backend |

Produção (`nklobmlxyidqxarzisph`) é este repositório parado na migration 11, com
23 migrations registradas: 11 stubs anteriores ao repo e 12 nossas (00–11).

---

## 1. Portões — antes de marcar a data

Nenhum destes é passo da janela. São condições para ela existir.

1. **P1 fechado**, com os cinco ajustes do revisor.
2. **Re-ensaio da fase 2 contra a pilha ATUAL**, em staging
   (`wbzaqjlfpqteesehapnn`), com os scripts que já existem —
   `scripts/ensaiar_rename_staging.sh` e `scripts/comparar_catalogos.py` — e o
   mesmo formato de resultado: catálogo comparado e suítes verdes.
   ⚠️ O ensaio que temos validou **11b + 12–15**. O que foi provado não é mais o
   que vai rodar: são 17 migrations agora, e as 16–27 nunca correram contra o
   schema de produção.
3. Só com os dois verdes é que a data é marcada com o cliente.

---

## 2. Pré-janela — o que tem de estar pronto ANTES, e não é reversível dentro dela

**O Railway está vazio.** Lido em 27/08/2026 pelo MCP: projeto `KastroPark`
(`eb5d0a6d-cc9b-42f8-b508-22f84f45db0c`), ambiente `production`, **zero
serviços**. Então "deploy do backend" na janela não é redeploy: é primeiro build,
primeiro boot, primeira leitura de env.

⛔ **Primeiro build não acontece dentro de janela.** O serviço tem de existir,
buildar e subir contra **staging** antes da data — o que a janela faz é trocar
para onde ele aponta e redeployar algo já provado. Um `uv sync` que falha às 2h
da manhã com a sincronização parada é um problema que não precisava existir.

Checklist de preparo:

- [ ] Serviço criado no Railway, buildando, apontado para staging
- [ ] Env do Railway preenchida (**nomes**, nunca valores neste documento):
      `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
      `SUPABASE_JWT_JWKS_URL`, `CORS_ORIGINS`, `IMPORT_BUCKET`, e ao menos uma de
      `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`
- [ ] Env da Vercel no projeto do painel: `NEXT_PUBLIC_SUPABASE_URL`,
      `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`
- [ ] `CORS_ORIGINS` com a origem exata do painel — `*` é rejeitado no startup
- [ ] Redirect URLs do Supabase Auth de produção incluem o domínio do painel
- [ ] **Exposed schemas de produção = apenas `public` e `graphql_public`**
- [ ] Backup completo e ponto de restauração criados

---

## 3. A janela, em ordem

A ordem não é preferência. Cada passo depende do anterior ter mudado o schema.

### Passo 0 — parar a escrita concorrente

Desabilitar os dois jobs de `pg_cron`. Eles escrevem durante o DDL e **nenhuma
Edge Function usa transação nos pontos que o §4b lista**.

| Job | Agenda |
|---|---|
| `sync-batidas-cron` | `*/15 * * * *` |
| `sync-cadastro-cron` | `*/30 * * * *` |

**Anotar o horário exato.** É o T0 do buraco na série. Com o horário de religar
(passo 6), é ele que diz se a parada coube nas 48 h da janela deslizante — o
único mecanismo de cobertura que produção tem (§5).

### Passo 1 — ponto de restauração

Depois da parada, não antes: um restore point tirado com a sincronização
correndo restaura para um estado que já mudou.

### Passo 2a — a limpeza que precede o lote

```
scripts/sb_sql.sh nklobmlxyidqxarzisph -f scripts/janela_pre_migrations.sql
```

Remove a policy duplicada `<tabela>_tenant_leitura` das quatro tabelas de
ingestão. **Sem isto a migration 24 aborta** com `app.batida_marcacao tem 2
policies, esperava 1`, no passo 14 de 17 — descoberto pelo re-ensaio de 27/08.

Não há mudança de autorização: as duas policies têm o mesmo comando, o mesmo
papel e o mesmo predicado (`util.has_tenant(tenant_id)`), e policies são
combinadas por OR. Se a janela abortar entre este passo e a 24, as quatro ficam
com RLS e zero policy — que nega tudo. Falha fechada, não aberta.

### Passo 2b — as migrations, uma chamada por migration

```
scripts/sb_sql.sh nklobmlxyidqxarzisph -f supabase/migrations/<arquivo>.sql
```

Na ordem: `11b` · `12` · `13` · `14` · `15` · `16` · `17` · `18` · `19` · `20` ·
`21` · `22` · `23` · `24` · `25` · `26` · `27` · **`28`**.

⛔ **A 28 não é opcional e não pode ficar para depois.** Ela reescreve
`deviation_read`, que o 11b renomeia sem traduzir o literal `'producao'` de
dentro da expressão. Enquanto ela não rodar, **todo não-admin vê zero desvios** —
sem erro e sem log. Aplicar o lote sem a 28 entrega um sistema que parece pronto
e mostra o painel vazio para o supervisor de unidade.

Cada chamada é atômica em si. **Entre elas não há atomicidade** — se a 19 falhar,
as anteriores estão aplicadas. É por isso que o ponto de restauração vem antes,
e não porque o rename possa ficar pela metade.

### Passo 3 — registrar as 18 em `supabase_migrations.schema_migrations`

Sem isso, o próximo `supabase db push` tenta aplicá-las de novo.

### Passo 4 — o runner da sincronização

⛔ **ESTE PASSO ESTÁ INCOMPLETO E BLOQUEIA A JANELA.** Ele dizia "deploy das Edge
Functions blindadas". Medido em 27/08: **produção não roda Edge Function
nenhuma.** `GET /v1/projects/<ref>/functions` devolve `[]`, e os dois jobs de
`pg_cron` chamam o serviço **`kastropark-jobs` na Vercel**
(`vercel_jobs_base_url` no Vault). O código dele não está neste repositório e
ainda não foi lido.

O que continua verdadeiro e decide a ordem: o runner tem de ser atualizado
**depois** do passo 2 e nunca antes. Quem grava `app.sync_run.scope` e
`records_skipped` depende da migration 21; e o runner antigo escreve nos nomes em
português que o 11b renomeia. Entre o passo 2 e o fim do passo 4 **não existe
sincronização funcional** — esse intervalo é a janela real.

⛔ **Além disso, o `kastropark-jobs` fala com o banco por PostgREST** — provado
em 27/08 quando remover `app`/`secullum` dos exposed schemas o derrubou com
`FUNCTION_INVOCATION_FAILED` (ver `INCIDENTE-2026-08-27-EXPOSED-SCHEMAS.md`).
Então **a correção dos exposed schemas é item DESTA janela**, junto com um runner
que não dependa mais deles. Nunca como mudança avulsa de painel.

⛔ **E ele escreve o diário errado.** O runner deste repositório grava em
`app.sync_run`; o `kastropark-jobs` grava em `app.job_execucao`, que **nenhuma
migration daqui cria**. Quem lê `app.sync_run` é `fn_data_freshness` — o deadman
de frescor, consumido pelo painel (`frontend/src/lib/freshness.ts`) e exposto
como métrica do assistente. Se o runner sair da janela ainda escrevendo só em
`job_execucao`, o deadman sobe **cego**: reporta toda entidade obsoleta sem que a
sincronização esteja quebrada.

Não se conserta com migration — a 12 não migra nada, ela só cria a função, o
índice e a linha de `app.metric`; e a 09 já cria a tabela, que em produção espera
o rename da 11b sob o nome `app.sync_execucao`. **É o runner que tem de mudar de
diário**, e por isso o requisito entra aqui e não no passo 2:

- [ ] o runner atualizado grava em `app.sync_run`, com `entity`, `scope`,
      `records_skipped` e `finished_at` — os campos que a 21 acrescentou e que
      `fn_data_freshness` agrupa
- [ ] uma execução real depois de religar aparece em `app.sync_run`, não só em
      `app.job_execucao`

Este passo só fica escrevível depois da leitura do `kastropark-jobs` — e a
leitura precisa responder **se ele consegue escrever em `app.sync_run`**, o que
depende de (b) da ordem fixada: por PostgREST, `app` teria de continuar exposto,
que é justamente o que esta janela remove.

### Passo 5 — backend no Railway

Redeploy apontando para produção. Não é aqui que ele nasce (ver §2).

### Passo 6 — religar, e o que de fato cobre o buraco

1. Reabilitar os dois jobs de `pg_cron`. **Anotar o horário**: com o T0 do passo
   0, é ele que dá o tamanho da parada — e o passo 7 precisa desse número.

2. ⛔ **Não há backfill a disparar.** Três medições de 27/08/2026 derrubam o que
   este passo mandava fazer:

   | Medido | Onde |
   |---|---|
   | os dois comandos chamam por **GET** — `command ~* 'post'` é falso nos dois | `cron.job` |
   | toda passada de batidas carimba **janela deslizante de 2 dias** | log do runner, `janela deslizante 2026-08-25..2026-08-27` |
   | nenhuma leitura mostrou o `kastropark-jobs` aceitando `scope` | leitura da Vercel |

   O `POST {"scope":"backfill"}` e o `BACKFILL_WINDOW_DAYS` são contrato do runner
   **deste** repositório, e produção não o roda desde 25/08.

3. **O que cobre o buraco é a janela deslizante.** Religados os jobs, as passadas
   seguintes releem os 2 dias inteiros e o upsert é idempotente — foi exatamente
   isso que absorveu o ciclo perdido do incidente de 27/08, sem deixar falha na
   série. **Enquanto a parada couber em 48 h, religar basta.** Passando disso, ver
   §5: não há gesto de recuperação ao nosso alcance.

⚠️ **Invocar à mão não é `curl` na URL.** O projeto está sob SSO
(`all_except_custom_domains`) e não tem domínio próprio, e a chamada leva o
segredo `vercel_cron_secret` — os dois vivem fora deste repositório. Existe ainda
um terceiro endpoint, `api/diagnostico`, que apareceu no build de 27/08 e **nunca
foi lido**; o que ele faz, e se dispara alguma coisa, é pergunta em aberto.

### Passo 7 — verificar que RELIGOU, não que respondeu

**Primeiro, o que a chamada de fato respondeu:**

```sql
select to_char(created at time zone 'America/Sao_Paulo','HH24:MI:SS') as quando,
       status_code, left(content, 90) as corpo
from net._http_response
where created > now() - interval '1 hour'
order by created desc;
```

⛔ **`cron.job_run_details` NÃO serve de evidência.** Ele marca `succeeded` por
ter entregado o `net.http_get` — as duas execuções que derrubaram a sync em
27/08 aparecem como sucesso ali. Quem guarda o resultado é `net._http_response`,
com `status_code` e `content`.

**Depois, que a ingestão voltou:**

```
python3 scripts/90_reconciliar_sync.py --dias 2
```

⛔ **E nem 200 basta.** O script afirma três coisas, e a terceira é a que não se
deduz de relatório nenhum:

1. a última execução de `Batida` terminou `completed`;
2. ela gravou linha (`records_written > 0`);
3. **nenhuma `Batida` na janela está sem marcação** — verificado contra o dado, e
   não contra o resumo, porque um resumo é o que o código achou que fez.

O item 3 é o estado que o motor lê como `no_punches` e transforma em indício
contra quem bateu ponto. Sai com código 1 em qualquer falha, para servir de
portão.

Rodar de novo **depois** de a janela deslizante ter passado sobre a parada
inteira. Não existe backfill a esperar — ver passo 6.

#### A cadeia 09 → 11b → 12, e por que este passo reprova por construção

| Migration | O que faz com o diário |
|---|---|
| **09** | cria o diário da sincronização. Produção recebeu a forma antiga: `app.sync_execucao`, 11 colunas, com `tenant_id`, `integracao_id`, `entidade` e contadores |
| **11b** | renomeia `app.sync_execucao` → `app.sync_run` e traduz as 8 colunas (`entidade`→`entity`, `terminado_em`→`finished_at`, …) |
| **12** | cria `public.fn_data_freshness` **sobre `app.sync_run`**, mais o índice parcial de frescor com `status = 'completed'` |
| 21 | acrescenta `scope` e `records_skipped` a `app.sync_run` |

⛔ **A 11b não menciona `app.job_execucao` uma única vez** — `grep -c job_execucao`
na migration devolve `0`. Ela renomeia o diário **vazio**. A cisão atravessa a
janela intacta, e nenhuma migration a fecha: é trabalho de runner, não de schema.

Medido em produção em 27/08/2026, por leitura:

| Diário | Linhas | Último fim |
|---|---|---|
| `app.sync_execucao` — o que a 11b renomeia para `app.sync_run` | **0** | — |
| `app.job_execucao` — o que o runner de fato usa | **220** | 27/08 21:30 BRT |

A inferência estrutural do §4b do plano deixa de ser inferência. E a consequência
é exata: com o lote aplicado e o runner intocado, `app.sync_run` segue vazio,
`fn_data_freshness` devolve **zero linha**, e `90_reconciliar_sync.py` para na
**afirmação 1** — *"app.sync_run não tem nenhuma execução de 'Batida'"* — saindo
com código 1. O passo 7 reprova, e reprova certo: quem não fechou foi o passo 4.

#### O que a conversão de diário exige — medido, não suposto

1. **Grão.** `app.job_execucao` tem uma linha por **job**: `job` só assume
   `sync_batidas` e `sync_cadastro`. `fn_data_freshness` agrupa por **entidade**, e
   `90_reconciliar_sync.py` procura `entity = 'Batida'`. Uma passada de cadastro
   carimba **17 entidades** no `resumo` (`companiesUpserted`, `unitsUpserted`,
   `employeesUpserted`, `schedulesUpserted`, `absencesUpserted`, …). Uma linha de
   job vira **N linhas** de `app.sync_run`, uma por entidade.
2. **Vocabulário de status.** O runner grava `running` / `success` / `error`;
   `app.sync_run` exige `running` / `completed` / `failed` / `partial`. `success`
   não é `completed`, e o índice de frescor da 12 filtra exatamente por
   `completed` — um mapeamento errado aqui sobe verde e mede nada.
3. ⛔ **Não há integração para referenciar.** `app.sync_run.integration_id` e
   `tenant_id` são `not null` com FK. Em produção, `app.integracao` tem **0
   linhas** (`app.tenant` tem 1). A primeira escrita em `app.sync_run` é
   impossível antes de alguém criar essa linha — **é linha nova em `app`, então é
   decisão do dono**, e ela precisa existir *antes* de o runner novo subir.
4. **Contadores.** `records_read`/`records_written` saem prontos do `resumo`:
   `batidasFetched`/`batidasUpserted` para `Batida`, os `*Upserted` por entidade
   no cadastro. O `records_skipped` da 21 também tem origem —
   `batidasSkippedMissingFuncionario` e `employeesSkipped`.
5. ⛔ **`app.job_execucao` também é o lock, e `app.sync_run` não tem equivalente.**
   O índice único parcial `job_execucao_em_andamento_key` — `(job) where status =
   'running'` — é o que impede duas passadas sobrepostas; o comentário da tabela
   em produção o declara ("lock de sobreposição dos jobs agendados"). Trocar de
   diário sem trocar de lock entrega sobreposição silenciosa. Então o alvo do
   passo 4 **não é "mudar de tabela"**: é escrever nos dois, ou dar o lock a
   `app.sync_run` antes de aposentar o outro. Decidir **antes** da janela.

---

## 4. Critério de saída

- [ ] `net._http_response` com `status_code = 200` nos ciclos após religar —
      **não** `cron.job_run_details`
- [ ] `90_reconciliar_sync.py` verde, duas vezes: no primeiro ciclo após
      religar, e de novo depois de a janela deslizante ter coberto a parada
- [ ] Um ciclo completo de cada job sem erro (15 min e 30 min)
- [ ] `fn_data_freshness` sem `is_stale` — limiar de 25 min para `Batida`.
      ⚠️ Este é o item que pega a **cisão de diário**: se ele acusar tudo
      obsoleto com a sincronização visivelmente rodando, o runner ficou gravando
      em `app.job_execucao` e o passo 4 não fechou. Conferir com
      `select entity, max(finished_at) from app.sync_run group by 1` antes de
      culpar a sync
- [ ] O painel abre contra produção e lista unidade e ocorrência
- [ ] `select count(*) from supabase_migrations.schema_migrations` = 41 (23 + 18)
- [ ] **Um supervisor de unidade vê os desvios da unidade dele.** É o que a 28
      conserta, e o que nenhum teste pegava: um usuário que não vê NADA passa em
      todo teste que só verifica o que ele não deve ver

---

## 5. Teto de parada — 48 h, e agora por medição

A Fase 3 dizia **48 h, e não era escolha**: `sync-batidas` lia uma janela fixa de
2 dias, `BATIDAS_WINDOW_DAYS` era constante de compilação, e a única forma de
alargá-la era um redeploy — dentro da janela, com a sincronização parada.

O P1 tirou essa amarra: janela como configuração, precedência
invocação > ambiente > padrão, escopo `backfill` relendo 7 dias.

⛔ **E nada disso vale em produção.** O P1 endureceu `supabase/functions/`, que
produção não roda desde 25/08. O que roda carimba, em **toda** passada,
`janela deslizante 2026-08-25..2026-08-27` — dois dias, fixos, lidos no log em
27/08/2026. **O teto de 48 h nunca caiu**; o que mudou é que antes ele saía da
leitura do nosso código e agora sai da medição do runner de verdade.

O que isso significa na prática:

- A janela é planejada em **horas**, e agora contra um teto duro. Parada acima de
  48 h deixa **buraco permanente** na série de marcações.
- **A folga de recuperação de 7 dias não existe aqui.** Ela é do runner deste
  repositório. Em produção, o único mecanismo de cobertura é a própria janela
  deslizante — passo 6.
- ⚠️ **Alargar a janela saiu do nosso alcance.** Antes era "um redeploy, ainda que
  no pior momento". O código está em `fdiasoliver/kastropark`, fora desta conta:
  esticar o teto virou **dependência de terceiro**, com o tempo de resposta dele
  no meio de uma janela com a sincronização parada. Então a parada se planeja para
  **caber** em 48 h, não para ser recuperada depois.
- ⚠️ **E há um segundo teto, que continua sem medição.** Por quanto tempo o
  Secullum ainda serve marcação retroativa não está escrito em lugar nenhum. Ele
  só passa a importar se alguém trocar o runner por um que releia mais que 2 dias
  — hoje o limite que morde primeiro é o de cima.

---

## 6. Rollback

| Passo | Reversível? |
|---|---|
| 0 — parada | sim, reabilitando os jobs |
| 2 — migrations | **não individualmente**. Só pelo ponto de restauração |
| 4 — Edge Functions | sim, redeploy da versão anterior — mas só faz sentido com o schema também restaurado |
| 5 — backend | sim, redeploy da versão anterior |

Restaurar o schema **obriga** a voltar as Edge Functions junto: as blindadas
escrevem colunas que só a 21 cria.
