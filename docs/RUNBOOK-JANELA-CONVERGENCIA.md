<!-- verificar-docs: inexistentes-de-proposito app.job_execucao app.sync_execucao app.integracao -->

# Runbook — janela de convergência

**Substitui a "Fase 3 — janela" de `PLANO-RECONCILIACAO-NUVEM.md`**, que ficou
desatualizada em dois pontos que mudam a operação inteira:

| | Fase 3, como escrita | Hoje |
|---|---|---|
| Migrations a aplicar | **5** (11b, 12–15) | **22** (11b, 12–32), mais a limpeza do passo 2a |
| Teto de parada | **48 h**, imposto pelo código | **48 h até a troca do runner, 7 dias depois dela** — ver §5 |
| Natureza da janela | rename | **release de convergência**: schema + Edge Functions + backend |

Produção (`nklobmlxyidqxarzisph`) é este repositório parado na migration 11, com
23 migrations registradas: 11 stubs anteriores ao repo e 12 nossas (00–11).

---

## 1. Portões — antes de marcar a data

Nenhum destes é passo da janela. São condições para ela existir.

1. **P1 fechado**, com os cinco ajustes do revisor.
2. ✅ **Re-ensaio da fase 2 contra a pilha ATUAL — rodado em 31/08/2026**, em
   staging (`wbzaqjlfpqteesehapnn`), contra o catálogo real de produção:

       22 migrations no lote                      todas ok
       97 / 98 / 99 / 98_postgrest                todas ok
       policies 70/70 · views 9/9 · funções 26/26
       RLS: 50 de 50 com FORCE
       enums pós-rename conferidos
       catálogo × alvo: só `app.job_execucao` diverge

   **O que este ensaio provou e o anterior não podia:** as migrations `29`–`32`
   entraram em 28/08, *depois* do ensaio de 27/08, e nunca haviam corrido contra
   um projeto Supabase de verdade. Duas delas criam tabela com policy nova. O
   portão tinha caído sem ninguém notar — que é exatamente o que ele existe para
   pegar.
   ⚠️ **O alvo precisa ser regerado junto.** `scripts/_alvo_en.json` era de
   27/08 e o passo 7 teria comparado com um alvo velho, dando verde falso. Rode
   `scripts/ensaiar_rename_nuvem.sh` antes, sempre que entrar migration nova.
   ⛔ **A divergência que sobra é a de sempre e é aceita:** `app.job_execucao`
   existe em produção e nenhuma migration daqui a cria — é o diário do runner da
   Vercel. O script sai não-zero por causa dela. Enquanto o `kastropark-jobs`
   não for lido, trazê-la para o repositório seria afirmar sobre um contrato que
   ninguém conferiu.
   ⚠️ **O passo 8 continua pulado** — a fronteira por HTTP no PostgREST real
   exige `SUPABASE_PUBLISHABLE_KEY` e `SUPABASE_SECRET_KEY` do **staging**. É o
   único braço que o ensaio não alcança, e o que ele cobriria é justamente onde
   o navegador vive.
   📌 **Um subproduto que vale para a janela:** o alvo confirma que os papéis
   seguem o rename. Produção tem `[owner, diretoria, rh, dp, …]` e o alvo tem
   `[owner, executive, hr, personnel, …]`, na mesma ordem — os vínculos gravados
   hoje em `app.tenant_membro` viram `owner` e `personnel` sozinhos.
3. ✅ **Os dois portões estão verdes desde 31/08.** A data pode ser marcada com o
   cliente.

---

## 2. Pré-janela — o que tem de estar pronto ANTES, e não é reversível dentro dela

~~**O Railway está vazio.**~~ Era o estado em 27/08/2026: projeto `KastroPark`
(`eb5d0a6d-cc9b-42f8-b508-22f84f45db0c`), ambiente `production`, **zero
serviços** — e foi o que tornou "deploy do backend" um primeiro build, não um
redeploy.

✅ **Deixou de valer em 28/08, e está medido em 31/08:** um serviço,
`operax-api`, no ambiente `production`, com `GET /health` respondendo **200
`{"status":"ok"}`**. O parágrafo acima fica porque é ele que explica por que o
próximo é uma regra e não um capricho.

⛔ **Primeiro build não acontece dentro de janela.** O serviço tem de existir,
buildar e subir contra **staging** antes da data — o que a janela faz é trocar
para onde ele aponta e redeployar algo já provado. Um `uv sync` que falha às 2h
da manhã com a sincronização parada é um problema que não precisava existir.

Checklist de preparo:

✅ **Feito em 28/08/2026** — os três primeiros itens abaixo. O serviço
`operax-api` existe no projeto `KastroPark` (ambiente `production` do Railway, o
único que há; quem aponta para staging são as variáveis), builda do
`backend/Dockerfile` com root directory `/backend`, healthcheck em `/health`, e
responde em **`https://operax-api-production.up.railway.app`**. O primeiro build
levou 15 s e a primeira falha foi a esperada — `ConfigurationError` nomeando as
quatro variáveis ausentes, que é o `config.py` recusando bootar meio
configurado. Duas correções que a primeira subida obrigou, e que valem para a
janela: `PORT=8000` fixo (o Railway injeta 8080 e o domínio aponta para 8000), e
`DATABASE_URL` no **session pooler (5432)**, não no transaction pooler (6543) —
`db.py` monta o pool sem `prepare_threshold=None`, e `?pgbouncer=true` o libpq
recusa como parâmetro desconhecido.

- [x] Serviço criado no Railway, buildando, apontado para staging
- [x] Env do Railway preenchida (**nomes**, nunca valores neste documento):
      `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
      `SUPABASE_JWT_JWKS_URL`, `CORS_ORIGINS`, `IMPORT_BUCKET`, e ao menos uma de
      `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`
- [x] Env da Vercel no projeto do painel: `NEXT_PUBLIC_SUPABASE_URL`,
      `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`
- [x] `CORS_ORIGINS` com a origem exata do painel — `*` é rejeitado no startup
      (conferido por HTTP: origem do painel recebe o header, origem estranha toma 400)
- [x] Redirect URLs do Supabase Auth de **produção** incluem o endereço do painel
      — **feito em 31/08** pela Management API: `site_url` e `uri_allow_list` com
      `https://operaxfonted.vercel.app`. `disable_signup` fica `true`, e o
      `http://localhost:3000` que o **staging** tem na lista **não** foi copiado:
      em staging serve ao desenvolvedor, em produção é um destino de redirect de
      autenticação numa porta local.
      ⏱️ **O primeiro `PATCH` respondeu 200 e a leitura seguinte ainda mostrava
      `localhost`** — a configuração propagou depois. Dentro da janela, conferir
      um ajuste de painel logo após aplicá-lo pode dar falso negativo, igual ao
      que já está registrado sobre a senha nova.
- [x] **Deployment Protection do projeto do painel desligada** — era ela que
      fazia toda URL devolver 302 para `vercel.com/sso-api`
- [x] Senha do banco de produção **resetada pelo painel** (Project Settings →
      Database) em 28/08, e **verificada** conectando pelas duas portas do pooler, e `DATABASE_URL` mais **três** dos quatro `SECULLUM_*`
      configurados como secrets das Edge Functions — ver passo 4. ⚠️ A redação
      anterior dizia "os quatro": a medição de 31/08 mostra `USERNAME`,
      `PASSWORD` e `CLIENT_ID`, **sem o `SECULLUM_BANK_ID`**.
      ⛔ **Não dá para roteirizar:** `alter role postgres with password` pelo
      `sb_sql.sh` responde `42501: only superusers can alter privileged roles` —
      a Management API roda como `postgres`, que no Supabase não é superusuário.
      Medido em 28/08 contra o staging. É passo manual do dono, e é por isso que
      está no preparo e não na janela.
      ⚠️ Escolha uma senha **URL-safe** (letras, dígitos, `-`, `_`). A que estava
      em `backend/.env.staging` tinha dois `@`, que o RFC 3986 obriga a escapar
      e que cada camada trata de um jeito — e além disso nem era a do staging.
      ⚠️ **A senha de produção foi exposta em canal de conversa em 31/08/2026.**
      **Decisão do dono, no mesmo dia: reset só ao concluir o projeto**, não
      antes da janela. Fica escrito o que a recomendação dizia, porque é o risco
      que o trabalho passa a carregar: hoje o custo de trocá-la é reconfigurar um
      secret (`DATABASE_URL` das Edge Functions), porque nada mais a consome —
      depois da janela ela sustenta a sincronização de produção e o backend, e a
      troca vira janela nova. **Item de encerramento do projeto**, ao lado da
      entrega de credenciais.
      ⏱️ **A senha nova não vale na hora.** Medido em 28/08 contra produção: o
      pooler recusou por alguns minutos depois do reset e passou a aceitar
      sozinho, sem nada ter mudado. Dentro da janela, `password authentication
      failed` logo após um reset **não é senha errada** — é propagação. Esperar e
      repetir antes de mexer em qualquer outra coisa
- [x] Backup **feito e provado** em 31/08 — e não pelo caminho que este runbook
      previa. ⛔ Medido: `pitr_enabled: false` e **zero backups listados** no
      projeto de produção, então o "ponto de restauração" do §6 não existia.
      Decisão do dono no mesmo dia: **dump lógico**. Foram dumpados os quatro
      schemas que carregam o que não volta sozinho (`app`, `secullum`, `util`,
      `public`) pelo **session pooler (5432)**, com `pg_dump` 17.6 — a mesma
      versão do servidor.
      ✅ **E o dump foi restaurado num Postgres descartável e conferido contra
      produção**: 176 funcionários, 4.822 marcações, 49 tabelas em `app`, 22 em
      `secullum`, 66 policies, 8 views. Backup que ninguém restaurou não é
      rollback. O banco de verificação foi apagado — tinha PII de 176 pessoas.
      ⚠️ O arquivo carrega `secullum` com PII completa e precisa de casa
      definitiva antes da janela; onde ele fica é decisão do dono.
- [x] **Ao menos um usuário em `auth.users`** — item que faltava nesta lista e é
      pré-requisito da curadoria, não da janela. Criado em 31/08 pelo Admin API,
      já confirmado (`mailer_autoconfirm` é `false`), com vínculo `owner` em
      `app.tenant_membro`. Provado sob RLS, como o usuário: `util.eh_admin` =
      true e as 4.822 marcações visíveis. O papel `owner` já tinha os quatro
      domínios sensíveis liberados desde a migration 02.

⛔ **Exposed schemas NÃO é item de preparo.** Ele parece um ajuste de painel e
não é: enquanto o runner atual falar PostgREST, corrigi-lo derruba a
sincronização — foi o incidente de 27/08. Ele é o item 4 do passo 4, depois de o
runner trocar.

**O endereço do painel é `operaxfonted.vercel.app`** (decisão de 28/08), e é ele
que entra no `CORS_ORIGINS` e nas Redirect URLs — o **alias do projeto**, nunca a
URL de deployment com hash, que muda a cada publicação e levaria o login junto.

⚠️ **A ordem entre os dois deploys não é livre.** `frontend/src/lib/env.ts`
valida `NEXT_PUBLIC_API_URL` como URL obrigatória e falha alto sem ela — medido
em 28/08: com o projeto sem variável nenhuma, `operaxfonted.vercel.app` respondia
**500 sem corpo**. O painel não sobe antes de existir uma API para apontar, nem
que seja a de staging. Railway primeiro, Vercel depois.

✅ **A pilha inteira foi provada contra staging em 28/08**, e é isso que o
preparo existe para conseguir: login pelo painel, `/me` devolvendo tenant e
papel, monitor diário com número por unidade, e o assistente respondendo uma
pergunta de período com evento `metrica` e agregado. Cada camada só apareceu
depois que a anterior fechou — e três defeitos só existiam com o serviço
publicado (a porta do `PORT`, o host IPv6-only e a migration 31).

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
`21` · `22` · `23` · `24` · `25` · `26` · `27` · **`28`** · `29` · `30` · **`31`** · `32`.

⛔ **A 28 não é opcional e não pode ficar para depois.** Ela reescreve
`deviation_read`, que o 11b renomeia sem traduzir o literal `'producao'` de
dentro da expressão. Enquanto ela não rodar, **todo não-admin vê zero desvios** —
sem erro e sem log. Aplicar o lote sem a 28 entrega um sistema que parece pronto
e mostra o painel vazio para o supervisor de unidade.

⛔ **A 31 é irmã da 28, e também não é opcional.** O 11b traduz `code` e
`target_view` de `app.metric` e **não** traduz `dimensions` e `filters`, que são
dado. Sem a 31, o catálogo de produção fica com nome de métrica em inglês e
parâmetro em português (`data_inicio`, `unidade`), e `catalogo.TYPES` — que é
código — levanta `UntypedParameterError` em **8 das 11 métricas**. A pessoa
recebe "Falha ao consultar o modelo", que é a mensagem de erro de *provider*,
com o provider funcionando e o token da pergunta já pago. Medida em staging, em
28/08, com o backend publicado.

Cada chamada é atômica em si. **Entre elas não há atomicidade** — se a 19 falhar,
as anteriores estão aplicadas. É por isso que o ponto de restauração vem antes,
e não porque o rename possa ficar pela metade.

### Passo 3 — registrar as 22 em `supabase_migrations.schema_migrations`

Sem isso, o próximo `supabase db push` tenta aplicá-las de novo.

⚠️ **Este passo deixou de ser decisão só nossa** (handoff da equipe de
plataforma, 28/08/2026). O histórico de migrations é **compartilhado**: eles
aplicam o que é deles via `supabase db query --file` justamente para não tocar
esse bookkeeping, e avisam que `supabase migration list` mostra migrations
"órfãs" dos dois lados. Registrar 22 versões nossas ali muda o que o CLI deles
enxerga.

Combinar antes, e **nunca** rodar `supabase migration repair` sem alinhar — é o
comando que pode confundir o CLI da outra equipe. Registrar é o certo para nós
(sem isso, um `db push` reaplica o lote); o que muda é que agora se avisa.

### Passo 4 — o runner da sincronização volta para este repositório

**Decisão de 28/08/2026 (do dono):** o `kastropark-jobs` sai, e as Edge Functions
deste repositório (`sync-cadastro`, `sync-batidas`, `secullum-test-auth`)
assumem a sincronização de produção. Este passo deixa de estar bloqueado — o
código dele nunca precisou ser lido, porque ele não vai continuar.

**O que a decisão destrava, e não é pouco:**

| | Com o `kastropark-jobs` | Com as funções daqui |
|---|---|---|
| Caminho até o banco | PostgREST — exige `app` exposto | conexão direta (`postgres-client.ts`) |
| Exposed schemas | impossível corrigir (foi o incidente de 27/08) | **corrigível nesta janela** |
| Diário de execução | `app.job_execucao`, que nenhuma migration daqui cria | `app.sync_run` — o que `fn_data_freshness` lê |
| Os quatro riscos do §4b | desconhecidos | corrigidos no P1 |

✅ **Compatibilidade com o schema pós-janela, conferida em 28/08.** As funções
gravam em `app.sync_run` (nome em inglês, pós-rename) e tocam as quatro tabelas
de ingestão pelos nomes em português — que o 11b **exclui do rename de
propósito**, e diz isso no próprio cabeçalho. Não há nada a renomear no runner.

⛔ **A MESMA SENHA GERA DUAS STRINGS DIFERENTES, E TROCÁ-LAS FALHA DEVAGAR**

Medido em 28/08 contra o staging, com o backend já publicado:

| Consumidor | Host e porta | Por quê |
|---|---|---|
| Edge Functions (`supabase/functions/`) | **Transaction Pooler, 6543** | `postgres-client.ts` já passa `prepare: false` e `max: 1` — desenhado para serverless |
| Backend FastAPI (Railway) | **Session Pooler, 5432** | `core/db.py` monta o pool sem `prepare_threshold=None` e usa `options=-c search_path`; o transaction pooler não sustenta nem um nem outro |

⛔ E **nenhum dos dois** é `db.<ref>.supabase.co`, a connection string que o painel
do Supabase mostra primeiro: aquele host é **IPv6-only**. O Railway sai por IPv4,
então a conexão não falha — ela **pendura** até o `PoolTimeout`, e o sintoma é um
500 de trinta segundos numa rota que parecia não ter nada a ver com rede. Custou
duas rodadas de diagnóstico em staging, onde não havia ninguém esperando.

✅ **Quatro dos cinco secrets já estão em produção — medido em 31/08/2026.**
As funções leem `DATABASE_URL`, `SECULLUM_USERNAME`, `SECULLUM_PASSWORD`,
`SECULLUM_CLIENT_ID` e `SECULLUM_BANK_ID`. A Management API (só nomes, nunca
valores) lista os quatro primeiros configurados. A senha do banco, que este bloco
dava como perdida, **foi resetada em 28/08** e é o que sustenta o `DATABASE_URL`
que está lá.

✅ **O `SECULLUM_BANK_ID` ausente é inofensivo nesta conta — medido em
31/08/2026.** `secullum-client.ts` o declara opcional: sem ele, `login()` escolhe
`banks[0]`. A conta tem **um banco só** (`88727`), então `banks[0]` é o único que
existe. Com mais de um, a sincronização espelharia o banco errado **sem erro e
sem log** — a classe de falha silenciosa que este runbook existe para não
repetir, e por isso a pergunta foi medida em vez de assumida.

**Como foi medido, e o que mais isso provou.** Autorizado pelo dono em 31/08, a
`secullum-test-auth` foi publicada em produção — só ela, e a premissa foi
conferida antes: a função **não abre conexão com o Supabase** (não importa
cliente de banco, não lê `DATABASE_URL`) e usa `/Horarios` de propósito, para não
tocar em PII. A invocação voltou `ok: true`, 1 banco, e 94 horários. **As três
credenciais do Secullum em produção estão corretas e funcionando** — o
pré-requisito de credencial do passo 4 está fechado, e fechado fora do relógio da
janela, que era o ponto.

💡 **Vale declarar o `SECULLUM_BANK_ID=88727` mesmo assim**, e é barato: hoje a
sincronização depende de a lista ter um elemento só. Se a conta do cliente ganhar
uma segunda empresa no Secullum, `banks[0]` muda sozinho e nada avisa.

A ordem interna continua a mesma, e pelo mesmo motivo: o runner sobe **depois**
do passo 2. `app.sync_run.scope` e `records_skipped` dependem da migration 21.
Entre o passo 2 e o fim deste passo **não existe sincronização funcional** — esse
intervalo é a janela real.

1. `supabase functions deploy` das três, com os cinco secrets já configurados.
2. Reescrever o comando dos dois jobs de `pg_cron`: hoje fazem **GET** no
   `vercel_jobs_base_url`; passam a invocar as funções. É a reescrita do comando
   que desliga a chamada à Vercel — não há gesto separado para isso.
3. ⚠️ **Conferir se o projeto da Vercel tem cron próprio** (`vercel.json`). Se
   tiver, ele precisa ser desligado lá: dois runners escrevendo o mesmo dado por
   dois caminhos mantêm dois cursores, e o upsert idempotente não protege contra
   isso.
4. **Só então** corrigir os exposed schemas para `public,graphql_public` — nesta
   ordem, e nunca antes de o passo 2 do item 2 estar valendo.

- [ ] uma execução real depois de religar aparece em `app.sync_run`, com
      `entity`, `scope`, `records_skipped` e `finished_at`
- [ ] `net._http_response` com 200 nos ciclos seguintes à correção dos exposed
      schemas — é exatamente o sinal que faltou em 27/08

### Passo 5 — backend no Railway

Redeploy apontando para produção. Não é aqui que ele nasce (ver §2).

### Passo 6 — religar, e o que de fato cobre o buraco

1. Reabilitar os dois jobs de `pg_cron`. **Anotar o horário**: com o T0 do passo
   0, é ele que dá o tamanho da parada — e o passo 7 precisa desse número.

2. ✅ **O backfill volta a existir — depois do passo 4.** As três medições
   abaixo, de 27/08/2026, descrevem o runner que sai, e ficam registradas porque
   explicam por que este passo mandava algo impossível enquanto ele estava lá:

   | Medido | Onde |
   |---|---|
   | os dois comandos chamam por **GET** — `command ~* 'post'` é falso nos dois | `cron.job` |
   | toda passada de batidas carimba **janela deslizante de 2 dias** | log do runner, `janela deslizante 2026-08-25..2026-08-27` |
   | nenhuma leitura mostrou o `kastropark-jobs` aceitando `scope` | leitura da Vercel |

   O `POST {"scope":"backfill"}` e o `BACKFILL_WINDOW_DAYS` são contrato do runner
   **deste** repositório — que é justamente o que o passo 4 devolve a produção.
   Depois dele, e só depois dele, o gesto de recuperação existe de novo.

3. **O que cobre o buraco é a janela deslizante.** Religados os jobs, as passadas
   seguintes releem os 2 dias inteiros e o upsert é idempotente — foi exatamente
   isso que absorveu o ciclo perdido do incidente de 27/08, sem deixar falha na
   série. **Enquanto a parada couber em 48 h, religar basta.** Passando disso,
   uma passada de `backfill` cobre até 7 dias — ver §5.

⚠️ **Isto vale enquanto o runner for o da Vercel.** Invocá-lo à mão não é `curl`
na URL: o projeto está sob SSO (`all_except_custom_domains`), não tem domínio
próprio, e a chamada leva o segredo `vercel_cron_secret` — os dois vivem fora
deste repositório. Depois do passo 4, invocar à mão é `supabase functions invoke`
com o corpo que `resolveRunOptions` lê, e o problema deixa de existir.

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
- [ ] `select count(*) from supabase_migrations.schema_migrations` = 45 (23 + 22)
- [ ] **O assistente responde uma pergunta de período** — "quantos desvios
      tivemos este mês?" tem de voltar com evento `metrica` e um número, não com
      "Falha ao consultar o modelo". É o item que pega a 31: catálogo e `TYPES`
      falando línguas diferentes só aparece com uma pergunta de verdade
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

⛔ **Nada disso valia em produção — até a decisão de 28/08.** O P1 endureceu
`supabase/functions/`, que produção não rodava desde 25/08. O que rodava
carimbava, em **toda** passada, `janela deslizante 2026-08-25..2026-08-27` —
dois dias, fixos, lidos no log em 27/08/2026.

**O teto de 48 h cai junto com o runner, e não antes dele.** Como o passo 4
devolve a sincronização às funções deste repositório, o que vale depois de
religar é o contrato delas: escopo `backfill` relendo 7 dias, janela como
configuração, precedência invocação > ambiente > padrão — e **sem redeploy**,
porque `resolveRunOptions` lê o corpo da invocação. Alargar a janela volta a ser
gesto nosso, em vez de depender de um repositório de terceiro no meio de uma
parada.

O que isso significa na prática:

- A parada continua planejada em **horas**. O que muda é a consequência de
  estourar: com o runner novo, uma parada acima de 48 h é **recuperável** com uma
  passada de `backfill`, em vez de virar buraco permanente.
- ⚠️ **O teto que sobra é o único que nunca foi medido:** por quanto tempo o
  Secullum ainda serve marcação retroativa. Ele deixou de ser hipotético no
  momento em que o runner passou a reler mais que 2 dias — agora é ele que morde
  primeiro, e continua sem número.
- ⛔ **Durante a janela, entre o passo 2 e o fim do passo 4, não há runner
  nenhum.** A folga de 7 dias é do lado de lá do passo 4; ela não cobre um passo
  4 que não terminou.

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
