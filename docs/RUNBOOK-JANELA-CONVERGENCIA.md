<!-- verificar-docs: inexistentes-de-proposito app.job_execucao app.sync_execucao app.integracao secullum.departamento_gestor secullum.departamento_gestor_transition -->

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
   ✅ **O passo 8 deixou de estar pulado — rodado em 31/08**, contra o
   PostgREST real do staging e já com o schema pós-janela: `POSTGREST OK`. anon
   toma 401 nas quatro views; `app`, `secullum` e `util` respondem **406 até
   para a chave de serviço**; a matview 404; cada sessão vê só o seu recorte;
   `tenant_id` vindo do cliente não fura a policy; `cpf` na superfície dá 400; e
   nenhuma view de `public` é gravável.
   ⛔ **As chaves NOVAS não servem para este projeto, e o sintoma engana.** A
   Management API lista `sb_publishable_…` e `sb_secret_…`, mas o PostgREST as
   recusa com **401**. Use as **legadas** (`anon` e `service_role`, os JWTs) —
   as duas saem de `GET /v1/projects/<ref>/api-keys`, sem precisar de ninguém.
   ⚠️ **E com a chave errada o passo 5 passa pelo motivo errado:** "anon recebe
   401" é verde tanto com a fronteira de pé quanto com a chave inválida. Quem
   denuncia são os `406` do passo 6 virando `401`. É a mesma patologia da
   asserção que conta zero numa tabela vazia — um teste que só verifica o que
   **não** deve acontecer passa quando nada acontece.
   📌 **Um subproduto que vale para a janela:** o alvo confirma que os papéis
   seguem o rename. Produção tem `[owner, diretoria, rh, dp, …]` e o alvo tem
   `[owner, executive, hr, personnel, …]`, na mesma ordem — os vínculos gravados
   hoje em `app.tenant_member` viram `owner` e `personnel` sozinhos.
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
- [ ] **A linha de `app.integration`** — `scripts/janela_integracao_secullum.sql`.
      Sem ela a janela fecha verde e o critério de saída reprova, porque a
      reivindicação da execução falha macio. Ver passo 7, item 3.
- [ ] **A migration 34 aplicada em produção** — o lock de sobreposição de
      `app.sync_run`. É pré-requisito do `functions deploy`, não item da janela:
      sem o índice, as funções novas param na primeira invocação. Produção está
      convergida até a 33 (ledger em 46), então esta é a única pendente. Ver
      passo 7, item 5.
- [ ] **Dois segredos novos no Vault de produção** — `edge_functions_base_url`
      (`https://<ref>.supabase.co/functions/v1`, sem barra final) e
      `edge_functions_token` (um JWT do projeto). Criados com
      `vault.create_secret()`. Sem eles `scripts/janela_cron_runner.sql` reprova
      antes de escrever, o que é o desenho — mas reprovar às 2h da manhã é
      preparo que não foi feito. Ver passo 4, item 2.
- [ ] **Decidir se o endpoint da sincronização pode ficar disparável por
      qualquer um.** Depois da troca, quem barra as Edge Functions é o
      `verify_jwt` do gateway, que aceita a anon key — que é pública. Não é
      vazamento; é custo e carga na origem. ✅ **A metade "passadas
      concorrentes" caiu em 02/09**: a migration 34 e a reivindicação em
      `sync-run.ts` deram a `app.sync_run` o lock que o `app.job_execucao`
      tinha, e uma invocação sobreposta agora recebe 409 sem chamar o Secullum.
      O que sobra é uma invocação de cada vez, fora de hora — fechar isso exige
      conferir um segredo compartilhado **dentro** das funções, que é mudança de
      contrato, e por isso segue no preparo.
- [x] **Ao menos um usuário em `auth.users`** — item que faltava nesta lista e é
      pré-requisito da curadoria, não da janela. Criado em 31/08 pelo Admin API,
      já confirmado (`mailer_autoconfirm` é `false`), com vínculo `owner` em
      `app.tenant_member`. Provado sob RLS, como o usuário: `util.is_admin` =
      true e as 4.822 marcações visíveis. O papel `owner` já tinha os quatro
      domínios sensíveis liberados desde a migration 02.

⛔ **Exposed schemas NÃO é item de preparo.** Ele parece um ajuste de painel e
não é: enquanto o runner atual falar PostgREST, corrigi-lo derruba a
sincronização — foi o incidente de 27/08. Ele é o item 4 do passo 4, depois de o
runner trocar.

**O endereço do painel é `operaxfonted.vercel.app`** (decisão de 28/08), e é ele
que entra no `CORS_ORIGINS` e nas Redirect URLs — o **alias do projeto**, nunca a
URL de deployment com hash, que muda a cada publicação e levaria o login junto.

⚠️ **Deixou de ser verdade, e a lista de produção ainda não sabe.** Medido em
01/09/2026 pela Management API e por HTTP: o painel vive em
**`app.fastparks.com.br`**, e `operaxfonted.vercel.app` responde **307** para lá.
A Redirect URL de produção nomeia o *redirecionador*, não o painel:

| Projeto | `site_url` | `uri_allow_list` |
|---|---|---|
| produção `nklob…` | `operaxfonted.vercel.app` | só ele e `/**` |
| staging `wbzaq…` | `app.fastparks.com.br` | os dois hosts + `localhost:3000` |

**Isso não quebra nada hoje, e o motivo importa mais do que o fato.** O painel
só usa `supabase.auth.signInWithPassword` — não há magic link, OAuth nem
recuperação de senha em `frontend/src/` (nenhum `emailRedirectTo`, nenhuma rota
`/auth/callback`). Fluxo de senha não consulta a allow list. O 307 também
preserva a query, conferido: `?code=TESTE123` chega inteiro ao outro host.

⛔ **Vira defeito no dia em que alguém adicionar "esqueci minha senha".** Aí o
painel pede `emailRedirectTo` do próprio host, produção recusa por não estar na
lista e cai calado no `site_url` — o usuário recebe um e-mail que o leva ao lugar
errado, sem erro em lugar nenhum. Corrigir é aditivo (acrescentar
`https://app.fastparks.com.br` e `/**` à lista), mas é escrita em configuração de
produção: **decisão do dono**, não item que se resolve de passagem.

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

1. ⚠️ **A migration 34 primeiro, o `functions deploy` depois.** Ela cria
   `sync_run_em_andamento_key`, o lock de sobreposição, e sem ela
   `claimSyncRun` estoura `there is no unique or exclusion constraint matching
   the ON CONFLICT specification` — a função falha alto, que é o desfecho certo
   e ainda assim é sincronização parada. Nenhum deploy aplica migration neste
   projeto; é passo à mão. Depois, `supabase functions deploy` das três, com os
   cinco secrets já configurados.
2. Reescrever o comando dos dois jobs de `pg_cron`: hoje fazem **GET** no
   `vercel_jobs_base_url`; passam a invocar as funções. É a reescrita do comando
   que desliga a chamada à Vercel — não há gesto separado para isso.

   ✅ **Deixou de ser comando na hora.** `scripts/janela_cron_runner.sql`, com
   as pré-condições falhando alto **antes** de qualquer escrita e uma guarda
   final que confere o que ficou. Reescreve os jobids 3 e 4 por
   `cron.alter_job` (que preserva o id; `update` direto em `cron.job` é negado)
   e agenda um terceiro:

   | job | cadência | destino |
   |---|---|---|
   | `sync-cadastro-cron` (3) | `*/30 * * * *` | `POST .../sync-cadastro` |
   | `sync-batidas-cron` (4) | `*/15 * * * *` | `POST .../sync-batidas` |
   | `sync-batidas-backfill` (novo) | `7 4 * * *` | `POST .../sync-batidas {"scope":"backfill"}` |

   O backfill é o que devolve o contrato da `SPEC-TECNICA.md` — correção na
   origem até D-7 vira revogação do indício. Com o runner da Vercel ele não
   existia. ⚠️ **O minuto 7 sai da grade de 15 de propósito**: em múltiplo de 15
   ele colidiria com o incremental. ✅ Desde 02/09 há lock (migration 34 + a
   reivindicação em `sync-run.ts`), e o minuto 7 passou de única proteção a
   redundância — fica como está, porque uma colisão que o lock resolve com 409
   é um backfill que não rodou naquele dia. A heurística
   de contagem do §3b passa a ser "96 + 48 + 1 por dia, e a única fora da grade
   é o backfill das 04:07 UTC".

   ✅ **Ensaiado** por `scripts/ensaio_janela_cron.sql`, que roda no
   `make db-test`: `cron` simulado, Vault de verdade, duas passadas provando
   idempotência, os jobids preservados e a guarda final exercitada **falhando**
   com um job deixado para trás. O que ele não prova é o `pg_cron` real — as
   funções ali são de mentira com a mesma assinatura.

   ⛔ **Dois pré-requisitos que não se resolvem dentro da janela:**

   - **Dois segredos novos no Vault**, `edge_functions_base_url` e
     `edge_functions_token`. Hoje só existem `vercel_jobs_base_url` e
     `vercel_cron_secret` (medido em 01/09). Reaproveitar os nomes deixaria o
     comando mentindo sobre para onde chama.
   - **O token não é o que protege o endpoint, e isso é decisão.** As três
     funções não conferem autorização nenhuma no corpo delas: quem barra é o
     `verify_jwt` do gateway, e ele aceita **qualquer** JWT do projeto —
     inclusive a anon key, que é pública. Depois da troca, quem tiver a anon key
     dispara uma sincronização. Não é vazamento (a resposta não carrega PII, por
     contrato das funções); é custo, carga na origem e — pior — `app.sync_run`
     **não tem** o equivalente do `job_execucao_em_andamento_key`, o índice único
     parcial que hoje impede duas passadas simultâneas. Fechar isso é mudança de
     contrato das funções, não do script.
3. ✅ **Não há cron próprio na Vercel — medido em 01/09/2026, e não por leitura
   de `vercel.json`.** O diário responde melhor que o arquivo: se houvesse um
   segundo invocador, apareceria execução fora da cadência do `pg_cron`. Em
   **7 dias e 928 execuções**, `sync_batidas` caiu 618 vezes e `sync_cadastro`
   310, e o minuto de início é sempre múltiplo de 15 — `{0,15,30,45}` para
   batidas, `{0,30}` para cadastro. **Uma única linha fora**, e ela tem
   explicação: `27/08 15:18:00`, 21 segundos depois de o último deploy da Vercel
   ficar `READY` (`15:17:49`) — é o smoke test de quem publicou, não um
   agendador.

   Isso fecha o item sem depender de ler o repositório de terceiro, que o `gh`
   desta conta não resolve. Fica valendo enquanto ninguém publicar lá: o último
   deploy do `kastropark-jobs` é de **27/08 15:17 UTC**, e não houve outro desde.
   Vale reconferir a contagem no dia da janela — é uma consulta só.
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
   `employeesUpserted`, `schedulesUpserted`, `absencesUpserted`, …).
   ⚠️ **A conclusão que este item tirava daí — "uma linha de job vira N linhas
   de `app.sync_run`, uma por entidade" — foi revista em 02/09.** É uma linha
   por passada, `entity = 'Funcionario'`; o porquê está no item 6.
2. **Vocabulário de status.** O runner grava `running` / `success` / `error`;
   `app.sync_run` exige `running` / `completed` / `failed` / `partial`. `success`
   não é `completed`, e o índice de frescor da 12 filtra exatamente por
   `completed` — um mapeamento errado aqui sobe verde e mede nada.
3. ⛔ **Não há integração para referenciar.** `app.sync_run.integration_id` e
   `tenant_id` são `not null` com FK. Em produção, `app.integration` tem **0
   linhas** (`app.tenant` tem 1) — remedido em **01/09/2026**, ainda vale. A
   primeira escrita em `app.sync_run` é impossível antes de alguém criar essa
   linha — **é linha nova em `app`, então é decisão do dono**, e ela precisa
   existir *antes* de o runner novo subir.

   ⚠️ **E a falta dela não faz barulho.** `recordSyncRun` não acha a integração,
   escreve no log e **volta**: a sincronização termina `ok: true`, as batidas
   entram, e `app.sync_run` fica vazia. A janela "dá certo" e o passo 7 reprova
   na afirmação 1 — o que se lê como "o runner novo não funciona", que é a
   conclusão errada.

   ✅ **`scripts/janela_integracao_secullum.sql`** cria a linha, é idempotente, e
   a guarda dela não confere só a existência: ela **grava de verdade** em
   `app.sync_run` com a integração recém-criada e desfaz a gravação num bloco
   aninhado. A consulta da guarda é copiada palavra por palavra do
   `recordSyncRun` — conferir por outro caminho provaria outra coisa. Ensaiado no
   `make db-test`, duas passadas, sem rastro.

   Efeito colateral conferido em 01/09: nenhum. Os dois leitores de
   `app.integration` são o `recordSyncRun` e o `_PROVIDER_SQL` de
   `backend/operax/alertas/outbox.py`, que filtra
   `provider in ('meta_cloud','z_api','uazapi')` — uma linha `secullum` é
   invisível para ele. O índice único da 14 também só alcança os três de
   WhatsApp, e nenhuma view de `public` lê a tabela.
4. **Contadores.** `records_read`/`records_written` saem prontos do `resumo`:
   `batidasFetched`/`batidasUpserted` para `Batida`,
   `employeesFetched`/`employeesUpserted` para `Funcionario`. O
   `records_skipped` da 21 também tem origem —
   `batidasSkippedMissingFuncionario` e `employeesSkipped`.
5. ✅ **`app.sync_run` ganhou o lock — 02/09/2026.** O índice único parcial
   `job_execucao_em_andamento_key` — `(job) where status = 'running'` — é o que
   impede duas passadas sobrepostas no diário do runner antigo; o comentário da
   tabela em produção o declara ("lock de sobreposição dos jobs agendados").
   Trocar de diário sem trocar de lock entregaria sobreposição silenciosa.

   O conserto tinha duas metades, e a de schema era a menor: a **migration 34**
   cria `sync_run_em_andamento_key` em `(tenant_id, entity) where status =
   'running'`, e `_shared/sync-run.ts` passou a **reivindicar antes e fechar
   depois** (`claimSyncRun` / `closeSyncRun`), nas duas funções. Enquanto era
   uma escrita só, no fim, já terminal, o índice seria um lock que nunca tranca.

   **A chave não inclui `scope`, de propósito:** `incremental` e `backfill`
   escrevem as MESMAS tabelas, então deixá-los correr juntos é a sobreposição
   que se quer evitar, não uma exceção a ela. Isso aposenta a heurística do
   minuto 7 do `scripts/janela_cron_runner.sql` — o backfill saía da grade de 15
   por não haver lock. O agendamento fica como está: agora é redundância, não
   a única proteção.

   ⛔ **O lease é a metade que faltava no enunciado, e sem ela o lock é pior que
   a doença.** Uma função que morre depois de reivindicar (timeout, deploy no
   meio, OOM) deixaria a linha `running` para sempre, e daí em diante **toda**
   execução seria recusada: crash transitório vira parada permanente. Por isso
   `claimSyncRun` encerra como `failed` o que passou do lease antes de
   reivindicar — o mesmo papel do "reaper de job_execucao" que apareceu no log
   do incidente de 27/08.

   **O lease de 10 min é medido, não escolhido.** Diário de produção em
   02/09/2026, 954 execuções: `sync_batidas` 3,5 s de média (máx 27 s),
   `sync_cadastro` 7,4 s (máx 31 s), e **zero linhas `running` presas**. Dez
   minutos são 20x o pior caso medido e menos que a menor cadência (15 min) —
   um `running` abandonado nunca sobrevive para bloquear o ciclo seguinte.

   ⚠️ **Ordem no passo 4: a migration 34 vem ANTES do `functions deploy`.**
   Conferido derrubando o índice e rodando o ensaio: sem ele o
   `on conflict ... where status = 'running'` estoura
   `there is no unique or exclusion constraint matching the ON CONFLICT
   specification`. A função **falha alto** (500) em vez de rodar sem lock — que
   é o desfecho certo, mas é sincronização parada se a ordem for invertida.

   ⚠️ **Uma invocação sobreposta passa a responder 409**, e isso não é o runner
   quebrado: é o lock funcionando. O critério de saída pede
   `net._http_response` com 200 — um 409 ali quer dizer que alguém disparou a
   função fora da cadência, que é exatamente o que a anon key pública permite
   (item 2 do passo 4).

6. ✅ **A `sync-cadastro` passou a escrever diário — 02/09/2026.** Até aqui só
   a `sync-batidas` chamava `recordSyncRun`, e isso era perda de
   observabilidade, não empate: hoje `app.job_execucao` tem uma linha a cada
   30 min para `sync_cadastro`, e foi por ela que a falha de autenticação de
   01/09 03:30 ficou visível. Depois da troca, uma falha de cadastro não
   apareceria em tabela nenhuma — só no log da Edge Function.

   `fn_data_freshness` não cobriria o buraco: ela agrupa pelo que existe em
   `app.sync_run`, não confere uma lista de entidades esperadas. Entidade que
   nunca escreve não vira linha velha — **vira ausência**, que nenhum painel lê
   como problema. E o passo 7 não reprovaria, porque `90_reconciliar_sync.py`
   só procura `entity = 'Batida'`.

   ⚠️ **Foi UMA linha por passada, e não uma por entidade** — o que este item
   e o item 1 diziam antes. A razão de mudar é medida:
   `runCadastroSync` **não tem `try/catch` em fase nenhuma**, então uma falha
   em qualquer ponto derruba a passada inteira. As 17 entidades do resumo
   sairiam sempre com o mesmo `started_at`, o mesmo `finished_at` e o mesmo
   `status` — 17 linhas idênticas nas três colunas que alguém lê, a cada meia
   hora, para um consumidor (`frontend/src/lib/freshness.ts`) que já reduz tudo
   à entidade mais velha. A entidade é `Funcionario`, que é o exemplo que a
   própria migration 09 dá para a coluna, e os contadores são
   `employeesFetched` / `employeesUpserted` / `employeesSkipped`.

   `employeesFetched` é novo no resumo, e não é enfeite: `records_read` derivado
   de `escrito + pulado` seria verdadeiro por construção, e é justamente essa
   soma que denuncia um caminho de saída novo no laço de funcionários que não
   incremente contador nenhum.

   O repositório nasce **antes** do `login()` na Edge Function, ao contrário da
   `sync-batidas`: a falha que mais precisa de rastro é a de autenticação, e
   criá-lo depois deixaria justamente ela sem com o que gravar. ⚠️ A
   `sync-batidas` mantém a ordem antiga e por isso continua sem registrar falha
   de login — o deadman de frescor ainda a pega (25 min sem `Batida`), mas o
   motivo fica só no log. Não foi mexido aqui: é a função que já está de pé.

   Provado no `make db-test`: `_shared/sync_espelho_test.ts` grava a linha com
   os contadores do ciclo real e a lê de volta. A guarda SQL de
   `janela_integracao_secullum.sql` prova que a tabela aceita a escrita, mas por
   uma cópia da instrução — só o ensaio prova que **alguém chama**. Conferido
   por sabotagem: sem a chamada, o teste reprova.

---

## 3b. Desfecho medido — 31/08/2026

A janela **converteu o schema e não trocou o runner**. As duas metades têm de
ser lidas separadas, porque só uma fechou.

### O que fechou

| Passo | Evidência |
|---|---|
| 0 · parar a escrita | `cron.alter_job` nos jobs 3 e 4 — **T0 = 18:10:03**. `update` direto em `cron.job` é negado: a tabela é do `supabase_admin` |
| 1 · ponto de restauração | dump lógico no T0, **restaurado e conferido**: 176 `Funcionario`, 4.822 batidas, 66 policies, 49 tabelas |
| 2a · limpeza pré-lote | `janela_pre_migrations.sql` |
| 2b · as 22 migrations | todas aplicadas **uma por chamada**, cada uma devolvendo `[]` |
| 3 · ledger | 45 = 23 + 22, o critério exato |

Estado pós-lote: **54 tabelas em `app`, 74 policies, zero sem RLS, 8 views
públicas, 11 métricas no catálogo**.

### O que não fechou, e por quê

**A troca do runner está bloqueada por divergência de schema no espelho.** A
`sync-cadastro` deste repositório grava `departamento_id` em
`secullum."Estrutura"`, e produção não tem essa coluna — o espelho de lá é
desenho da outra equipe.

A causa raiz é mais larga que esse sintoma, e foi medida:

> **As 22 tabelas do schema `secullum` e a `app.job_execucao` existem apenas em
> produção.** Nenhuma migration deste repositório as cria. Local e staging não
> têm espelho nenhum.

Disso decorre que **nenhum ensaio jamais executou as Edge Functions deste
repositório contra um espelho real** — não por descuido, mas porque não havia
contra o que executar. Todo ensaio validou o lado `app`.

#### ⚠️ 01/09/2026 — o parágrafo acima está errado, e o certo é pior

A frase "não havia contra o que executar" não sobreviveu à primeira tentativa de
construir o alvo. **Havia.** O `make db-test` monta 20 das 22 tabelas de
`secullum` desde 24/08: `scripts/_baseline.sql` as cria em `public`, e a
migration 03 as varre para `secullum`. O que o ensaio não tinha eram as duas
snake_case — a 03 só varre `^[A-Z]`, e o que é minúsculo ela manda para `app`.

O alvo existia. Ele estava **velho**, e a deriva contra produção era de três
linhas:

```
  departamento_id uuid not null,                          ← em "Estrutura"
  ...estrutura_departamento_id_fkey FOREIGN KEY (departamento_id)
  CREATE INDEX "Estrutura_departamento_id_fkidx"
```

As três são a mesma coisa, e é exatamente a coluna que bloqueou a troca do
runner. Em 21/08 a outra equipe fez backfill de `"Estrutura".departamento_id`
para `secullum.departamento_gestor` — tabela historizada, escrita só por
`secullum.departamento_gestor_transition()` — e derrubou a coluna. O baseline de
24/08 ainda a tinha, então a `sync-cadastro` daqui passava verde em toda suíte
enquanto era impossível em produção.

**A lição muda de lugar.** Não é "faltava capturar o espelho": é que o espelho
capturado não tinha dono nem conferência, e envelheceu em silêncio — o mesmo
modo de falha dos gatilhos de toque, três parágrafos abaixo. Um alvo sem
verificação é um alvo que mente com a idade.

O que passou a existir em 01/09:

| Peça | Trabalho |
|---|---|
| `supabase/fixtures/espelho_secullum.sql` | produção capturada do catálogo, e as 2 tabelas snake_case + a função da outra equipe que o caminho do baseline não entrega |
| `scripts/verificar_espelho.py` | confere os dois lados — ensaio contra a fixture (na suíte, sem rede) e fixture contra produção (antes de marcar janela) |
| `scripts/88_teste_espelho.sql` | 22 tabelas · RLS em todas · `force` nas 20 PascalCase · nenhum grant para `anon`/`authenticated` · ponte da 24 fechada |
| `scripts/_baseline.sql` regenerado | as 20 PascalCase com as colunas de hoje |

E o conserto que a medição obrigou: `upsertManagers` **parou de gravar
`departamento_id`** em `"Estrutura"`. Nada neste repositório lia esse vínculo —
`app.manager` (migration 27) o resolve por `Funcionario.EstruturaId` — então
remover a escrita não perde informação que alguém use. ⏳ **Manter
`departamento_gestor` continua não implementado**: exige a semântica do ADR-013,
documento que não está neste repositório.

### A regressão que a janela causou, e o conserto

Religar os jobs às 18:38 **não** restabeleceu a sincronização. As batidas
falharam em todo ciclo até as 22:33:

```
record "new" has no field "updated_at"
```

A `11b` renomeou a função de toque — `toca_atualizado_em`, nome que deixou de
existir — para `util.touch_updated_at` e
reescreveu o corpo para gravar `new.updated_at`. As quatro tabelas de ingestão
ficaram fora da renomeação **de propósito**. Mas produção tem, em duas delas,
gatilhos `trg_atualizado_em` que a outra equipe criou e que este repositório
nunca teve — e a renomeação seguiu a função debaixo deles.

O `insert` continuava passando: o gatilho é `before update`, e a escrita da
sincronização é upsert de janela deslizante, que atualiza. Por isso falhou
exatamente na sincronização e em mais nada.

Consertado pela **migration 33**, aplicada em produção (ledger → 46), com as
duas metades: uma função de toque em português para as tabelas em português, e
a asserção que faltava — *todo gatilho de toque grava numa coluna que a tabela
tem*. A falha foi reproduzida localmente antes do conserto, com a mensagem
idêntica.

⚠️ **Isto é a mesma cegueira do bloqueio do `Estrutura`, em outro sintoma.** O
alvo tem objetos que o ensaio não tem, então o ensaio não pode falhar por causa
deles. Uma revisão por texto também não pega: nenhuma das 22 migrations cita
esses gatilhos — o alcance foi indireto, pela função.

### A cisão de diário deixou de ser risco e virou medição

O critério de saída previa `fn_data_freshness` como o item que pegaria isso.
Ele pega — só não da forma esperada, porque **não devolve linha nenhuma**:

| Diário | Registros em 31/08 |
|---|---|
| `app.sync_run` — o que `fn_data_freshness` lê | **0** |
| `app.job_execucao` — o que o runner da Vercel escreve | **800** |

Enquanto o runner for o da Vercel, o indicador de frescor do painel fica cego
por construção, e nenhum usuário vê que o dado atrasou. Não é bug a corrigir
agora: é mais uma consequência de o runner não ter sido trocado, e some junto
com ela. Registrado para não ser diagnosticado do zero na próxima janela.

### Estado ao fim da janela

- ✅ Schema convergido, ledger em 46, zero tabelas sem RLS
- ✅ Sincronização rodando — **no runner antigo**, o `kastropark-jobs` da Vercel
- ⛔ `exposed schemas` **permanece** `public,graphql_public,app,secullum`, e a
  permanência é decisão: enquanto o runner falar PostgREST, corrigi-lo derruba
  a sincronização. Foi o incidente de 27/08
- ⛔ Backend do Railway ainda apontado para staging

### 01/09/2026 — a linha de base que a janela não pode piorar

Medido hoje pelo `app.job_execucao` de produção, que é o diário do runner atual.
Existe porque "a sincronização voltou" não é afirmação verificável sem um número
de antes:

| Classe de erro | Ocorrências em 48 h | Primeira | Última |
|---|---|---|---|
| gatilho `updated_at` em `app.batida_marcacao` | 16 | 31/08 21:45 | **01/09 01:30** |
| `Falha ao autenticar no Secullum (HTTP 500)` | 2 | 01/09 03:30 | 01/09 19:30 |
| `Secullum retornou HTTP 503` (GET Batidas / Funcionarios) | 2 | 31/08 00:00 | 31/08 00:00 |

✅ **A migration 33 está provada por comportamento, não por ledger.** A série de
16 falhas termina às 01:30 de hoje e não reaparece em 81 execuções seguintes de
`sync_batidas`. Ledger em 46 diz que ela foi *aplicada*; o fim da série diz que
ela **funcionou**.

O que sobra são 4 falhas em 48 h, todas do lado da origem (500 e 503 do
Secullum), contra 96 execuções de batidas e 48 de cadastro por dia. **~2 % de
falha transitória é o normal a bater depois da troca de runner** — acima disso,
o problema é a troca, não o Secullum.

Volume no mesmo momento: 176 funcionários, 1.576 linhas em `secullum."Batida"`,
5.118 em `app.batida_marcacao` (eram 4.822 em 31/08 — está crescendo), última
data de batida **01/09**. Zero tabelas de `app` sem RLS, 8 views em `public`.

✅ **O espelho confere contra produção** — `scripts/verificar_espelho.py
nklobmlxyidqxarzisph`, 1.305 linhas de DDL idênticas. É a conferência que o
`CLAUDE.md` exige antes de marcar data, e ela está verde hoje.

### O que a próxima janela precisa antes de ser marcada

1. ✅ **Feito em 01/09.** O schema real de `secullum` capturado neste
   repositório e, mais importante, **conferido a cada `make db-test`** — a
   captura sozinha era o que já existia e mentia. Ver o adendo de 01/09 acima.
2. ✅ **O ciclo de cadastro correu contra o espelho, e passou** — primeira vez
   nesta base. `_shared/sync_espelho_test.ts` roda `runCadastroSync`
   com origem falsa e **banco real**, e reprova alto em `42703`/`42P01`. O
   caminho curto que o torna barato: `column does not exist` é erro de *parse*,
   levantado antes de qualquer constraint — então um ciclo que atravessa sem
   ele já provou que as 21 escritas são dizíveis contra o schema de produção.
   Roda no `make db-test` quando `ENSAIO_DATABASE_URL` está definida, e diz
   alto quando não roda.

   ⚠️ **Ele reprovou de primeira, e por um defeito da ferramenta da manhã.**
   `secullum."Empresa".ativo` é coluna GERADA em produção
   (`coalesce(not "Desativada", true)`), e a captura perdia a cláusula
   `generated always as`: no ensaio ela virava coluna comum `not null` sem
   default, e o `upsertCompanies` — que a omite justamente por ela ser gerada —
   estourava. **O verificador de drift jamais pegaria isso**, porque passa os
   dois lados pelo mesmo renderizador e a perda se cancela. Consertado nos dois
   geradores; quatro fixtures de teste que escreviam `ativo` foram alinhadas.

   ✅ **`sync-batidas` também.** `_shared/sync_espelho_test.ts` roda os dois
   ciclos na ordem em que a realidade os põe — cadastro cria o funcionário,
   batidas se correlaciona a ele — e juntos atravessam as 17 tabelas do espelho
   que os repositórios escrevem, mais `app.batida_marcacao` e os dois diários
   de evento. A carga é única por execução, porque a sincronização é idempotente
   e uma segunda passada zeraria os contadores: sem isso a asserção "escreveu"
   só valeria em banco recém-criado.

   ✅ **`secullum.departamento_gestor` passou a ser mantida** — com premissa
   declarada, porque o ADR-013 não está neste repositório. A regra foi derivada
   das 25 linhas de produção medidas em 01/09 e dos comentários da própria
   tabela, e mora numa função pura (`decideDepartmentManagerTransitions`) para
   que um teste possa contradizê-la:

   | Evidência | Regra que ela sustenta |
   |---|---|
   | `funcionarios_observados`: *"proibido eleição por maioria — ADR-013 §4/§4.1"* | maioria **não** elege; o campo é diagnóstico |
   | departamento `192733c0`: 2 Estruturas (2 e 1 ativos), **zero linhas** | atribuição inicial só quando **inequívoco** |
   | departamento `d9b91b52`: vigente com 2 ativos, segunda Estrutura com 1 | uma vez vigente, **gruda** enquanto observada |
   | a RPC exige `p_estrutura_id`; um departamento sem ativos segue aberto | **não existe fechar sem substituto** |

   ⚠️ **Era aqui que eu ia errar.** A regra que eu inferiria — maioria dos
   colaboradores — é exatamente a que o comentário da tabela proíbe. Foi ler o
   espelho, e não raciocinar sobre ele, que evitou escrever história errada numa
   tabela de outra equipe.

   A escrita vai pela RPC `secullum.departamento_gestor_transition`, que é o
   único caminho permitido: ela fecha a anterior e abre a nova numa transação
   só. O ensaio exercita essa chamada contra o espelho real.
3. ✅ **O bloqueio real do item 2 caiu em 01/09: `secullum-cadastro-types.ts`
   não existia.** `cadastro-sync.ts` importava 15 tipos dele, e o módulo não
   estava nem aqui nem na nuvem — `import type` some na transpilação, então ele
   nunca chegou ao deploy e o `functions download` não o trazia. O deploy
   funcionava; o `deno check` não passava; e **não havia tipo contra o qual
   construir a carga de um ensaio**. Era esse o motivo de fundo de "as funções
   nunca correram contra o espelho", não a falta de alvo.

   Reconstruído pelo método do irmão `secullum-batida-types.ts`: **pelo
   compilador, campo a campo, a partir de cada acesso que o código faz** — não
   do que a origem promete, e não do que o espelho guardou. Com as 15
   interfaces vazias, `deno check` lista cada propriedade que falta e em qual
   tipo; foram **275**, em quatro rodadas. O espelho serviu de conferência
   (`RawFuncionario` 72 campos x 77 colunas), não de fonte.

   A tipagem é permissiva de propósito: os leitores recebem `unknown` e validam
   em runtime, e tipo forte só onde o código atribui direto. Declarar
   `Nome: string` sem isso afirmaria sobre o Secullum uma garantia que ninguém
   pode conferir — não há sandbox dele para este cliente.

   Resultado medido: **`supabase/functions/` inteiro type-checa** — os doze
   módulos de `_shared` e os três entrypoints. Os 12 erros que sobravam eram
   duas coisas, nenhuma delas contrato com a origem:

   - as listas de coluna eram `string[]`, e o helper `sql(rows, ...columns)`
     quer `(keyof T)[]` — resolvido com `as const`, que não muda uma linha de
     runtime;
   - `buildFuncionarioRow` declarava retorno `Record<string, unknown>`, o que
     **apagava a forma da linha**: o spread dela não contribuía chave nenhuma e
     as colunas deixavam de casar. Resolvido deixando o TypeScript inferir.

   Com isso o `deno.json` perdeu o `--no-check` que carregava desde 25/08, e
   `deno task check` passou a cobrir tudo. O único cast novo está em
   `asJsonPassthrough`, e ele não afirma shape — diz "isto é JSON", que é o que
   a coluna `jsonb` do espelho já declara. Modelar as colunas do item é
   justamente o que os comentários daquele campo proíbem por falta de
   evidência.
4. Só então os passos 4 a 7, na ordem em que já estão escritos.

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
- [ ] **Duas entidades em `fn_data_freshness`, não uma** — `Batida` e
      `Funcionario`. Desde 02/09 a `sync-cadastro` também escreve o diário
      (passo 7, item 6), e é aqui que se vê se ela escreveu: entidade que nunca
      grava **não fica velha, some** — e um `is_stale` limpo com uma entidade só
      é o mesmo verde de quando o cadastro não estava rodando
- [ ] O painel abre contra produção e lista unidade e ocorrência
- [x] `select count(*) from supabase_migrations.schema_migrations` = 45 (23 + 22)
      — atingido em 31/08. **Passou a 46** com a migration 33, que consertou
      a regressão descrita na seção 3b; 45 continua sendo o número que
      fecha o lote, não o número final do ledger
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
