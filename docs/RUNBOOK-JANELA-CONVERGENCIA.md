# Runbook — janela de convergência

**Substitui a "Fase 3 — janela" de `PLANO-RECONCILIACAO-NUVEM.md`**, que ficou
desatualizada em dois pontos que mudam a operação inteira:

| | Fase 3, como escrita | Hoje |
|---|---|---|
| Migrations a aplicar | **5** (11b, 12–15) | **17** (11b, 12–27) |
| Teto de parada | **48 h**, imposto pelo código | Não é mais o código que impõe — ver §5 |
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

**Anotar o horário exato.** É o T0 do buraco na série, e é ele que o backfill do
passo 6 precisa cobrir.

### Passo 1 — ponto de restauração

Depois da parada, não antes: um restore point tirado com a sincronização
correndo restaura para um estado que já mudou.

### Passo 2 — as 17 migrations, uma chamada por migration

```
scripts/sb_sql.sh nklobmlxyidqxarzisph -f supabase/migrations/<arquivo>.sql
```

Na ordem: `11b` · `12` · `13` · `14` · `15` · `16` · `17` · `18` · `19` · `20` ·
`21` · `22` · `23` · `24` · `25` · `26` · `27`.

Cada chamada é atômica em si. **Entre elas não há atomicidade** — se a 19 falhar,
as anteriores estão aplicadas. É por isso que o ponto de restauração vem antes,
e não porque o rename possa ficar pela metade.

### Passo 3 — registrar as 17 em `supabase_migrations.schema_migrations`

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

Este passo só fica escrevível depois da leitura do `kastropark-jobs`.

### Passo 5 — backend no Railway

Redeploy apontando para produção. Não é aqui que ele nasce (ver §2).

### Passo 6 — religar e cobrir o buraco

1. Reabilitar os dois jobs de `pg_cron`.
2. Disparar o backfill explicitamente, sem esperar a passada diária:

   ```
   POST <url da sync-batidas>   body: {"scope":"backfill"}
   ```

   Cobre 7 dias (`BACKFILL_WINDOW_DAYS`). Se a parada tiver passado disso, a
   janela é ajustável **na própria invocação**, sem redeploy:
   `{"scope":"backfill","windowDays":N}` — a precedência é invocação > ambiente >
   padrão do código.

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

Rodar de novo **depois** do backfill do passo 6.

---

## 4. Critério de saída

- [ ] `net._http_response` com `status_code = 200` nos ciclos após religar —
      **não** `cron.job_run_details`
- [ ] `90_reconciliar_sync.py` verde, duas vezes: após religar e após o backfill
- [ ] Um ciclo completo de cada job sem erro (15 min e 30 min)
- [ ] `fn_data_freshness` sem `is_stale` — limiar de 25 min para `Batida`
- [ ] O painel abre contra produção e lista unidade e ocorrência
- [ ] `select count(*) from supabase_migrations.schema_migrations` = 40 (23 + 17)

---

## 5. Teto de parada — o que o P1 mudou

A Fase 3 dizia **48 h, e não era escolha**: `sync-batidas` lia uma janela fixa de
2 dias, `BATIDAS_WINDOW_DAYS` era constante de compilação, e a única forma de
alargá-la era um redeploy — dentro da janela, com a sincronização parada.

O P1 tirou essa amarra. A janela virou configuração com precedência
invocação > ambiente > padrão, e o escopo `backfill` relê 7 dias com o mesmo
upsert do incremental. **Uma parada longa passou a ser recuperável sem
redeploy.**

O que isso significa na prática:

- A janela continua sendo planejada em **horas**. Nada aqui é convite a esticá-la.
- O que cresceu é a **folga de recuperação**: 7 dias por padrão, e mais que isso
  por `windowDays` explícito. É folga de *rollback* — se algo falhar no meio e for
  preciso restaurar, tentar de novo e só então religar, o buraco resultante
  continua coberto.
- ⚠️ **O limite real deixou de ser o nosso código e passou a ser a origem.** Por
  quanto tempo o Secullum ainda serve marcação retroativa não foi medido, e não
  está escrito em lugar nenhum. Enquanto ninguém medir, tratar 7 dias como o teto
  operacional — não porque o código imponha, mas porque é o que já foi exercido.

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
