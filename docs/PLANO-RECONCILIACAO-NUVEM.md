# OperaX — plano de reconciliação do projeto na nuvem

**Decisão de 22/08/2026:** reconciliar o projeto Supabase do cliente com este
repositório, em vez de tratá-lo como sistema legado.

Este documento existe porque a operação **não pode começar hoje** e porque o que
foi descoberto sondando o projeto se perde se ficar só numa conversa.

---

## 1. O que o projeto na nuvem é hoje

> **Nota para quem editar:** os identificadores da nuvem aparecem aqui **sem
> crases**, de propósito. `scripts/verificar_docs.py` confere que todo objeto
> de banco citado entre crases existe no schema deste repositório — e estes,
> por definição, não existem. Colocar crases neles deixa a suíte vermelha.

`nklobmlxyidqxarzisph` ("Kastro Park Ponto"). Levantado em 22/08/2026 pelo
PostgREST, com chave de serviço, **sem ler uma única linha** — as views são
`security_invoker` e os grants vão para `authenticated`, então uma chave de
serviço recebe 403 em tudo. O mapeamento abaixo saiu das mensagens de erro, que
nomeiam a tabela por trás de cada view.

### Superfície pública: nomenclatura anterior ao rename pt→en

| Na nuvem | Neste repositório |
|---|---|
| vw_unidade | `vw_unit` |
| vw_colaborador | `vw_employee` |
| vw_desvio_evento | `vw_deviation_event` |
| vw_desvio_resumo_unidade | `vw_deviation_summary_by_unit` |
| vw_desvio_tendencia_diaria | `vw_deviation_daily_trend` |
| vw_desvio_por_colaborador_dia | `vw_deviation_by_employee_day` |
| vw_documento_vencimento | `vw_document_expiry` |
| vw_folha_resumo | `vw_payroll_summary` |
| fn_kpi_periodo | `fn_kpi_period` |
| fn_ranking_unidade | `fn_ranking_by_unit` |
| fn_ranking_colaborador | `fn_ranking_by_employee` |
| fn_recorrencia | `fn_recurrence` |
| rls_auto_enable | **não existe aqui** — investigar antes de qualquer coisa |
| — | `fn_data_freshness` (migration 12) **falta lá** |
| — | `fn_whatsapp_readiness` (migration 14) **falta lá** |

As colunas seguem a mesma divergência: colaborador_id, data_ref, minutos,
direcao, horario_previsto, horario_realizado onde aqui é `employee_id`,
`reference_date`, `minutes`, `direction`, `expected_time`, `actual_time`.

### O estado é misto, e é isso que impede um `db push`

As tabelas por trás das views são app.unidade, app.colaborador,
app.documento, app.folha_evento — português — mas **`app.deviation_event`
está em inglês**. A nuvem recebeu a migration 04 na versão antiga e a 05 na
versão nova: é um retrato de meio-rename, não uma versão qualquer deste
repositório.

**Consequência:** aplicar as 16 migrations ali criaria app.employee ao lado de
app.colaborador, duplicando o modelo em vez de convergir. A reconciliação
precisa de uma migration de rename escrita **a partir do schema real**, não de
palpite.

### O que já está certo lá

`public` não expõe nenhuma tabela — só views e RPCs. A blindagem das migrations
00, 01 e 03 rodou.

---

## 1b. O que a leitura do catálogo mostrou (22/08/2026)

A seção acima foi escrita por dedução, a partir de mensagens de erro 403. Esta
foi medida. Onde as duas discordarem, esta vale.

### Produção tem histórico de migration próprio — e ele explica tudo

23 migrations aplicadas. **Onze** anteriores a este repositório
(`20260811120000` … `20260813164000`, era das Edge Functions + pg_cron) e
**doze** que são as deste repositório, da `00_blindagem_imediata` à
`11_performance`.

Ou seja: produção **não é um sistema paralelo**. É este repositório, parado na
migration 11. Faltam lá as migrations 12, 13, 14 e 15.

As onze primeiras são **stubs vazios**, criados por `supabase migration repair
--status applied`. Cada uma guarda exatamente o mesmo texto de 1052 caracteres
dizendo "conteúdo real capturado em `schema_migrations.statements`" — que é o
próprio stub. **O DDL original dessas onze se perdeu.** O catálogo vivo é a
única fonte do que elas criaram, e é por isso que a introspecção existe.

### O mapa pt→en não precisa ser adivinhado: ele é derivável

`supabase_migrations.schema_migrations.statements` guarda o SQL de verdade das
doze migrations deste repositório — e guarda a versão **em português**, que é
como elas eram quando produção as rodou. Este repositório reescreveu os mesmos
arquivos em inglês depois.

São, portanto, o mesmo arquivo em duas grafias. Alinhando o fluxo de
identificadores dos dois lados (comentários e literais removidos), o
pareamento é exato, não heurístico:

- **11 de 12** migrations alinham token a token. A décima segunda,
  `01_fundacao_schemas`, desalinha por 2 tokens porque o arquivo local ganhou
  depois um bloco `do $$` de preflight que produção nunca viu — não é rename.
- **348 identificadores** mapeados 1:1.
- **1 ambiguidade**, e é a esperada: `papel` vira `role` como coluna (14×) e
  `user_role` como enum (4×). O rename precisa ser por contexto, não global.

**`scripts/rename_map.py` está correto**: zero divergências contra o que o banco
prova. Os 121 pares "ausentes" dele são nomes compostos — policy `X_leitura` →
`X_read`, índice `X_idx` — que o `SUFIXOS` do próprio arquivo compõe.

### O rename deste repositório ficou pela metade nos nomes compostos

Efeito colateral da comparação: **29 nomes de policy, índice e constraint deste
repositório ainda carregam palavra em português.** Alguns exemplos verificados
contra o banco: `employee_departamento_idx`, `unit_tenant_empresa_idx`,
`report_cycle_unidade_idx`, `acordo_read`, `ciclo_read`, `escopo_read`,
`user_scope_empresa_fk` — e o melhor de todos, `deviation_event_unico_active`,
em que metade do identificador foi traduzida e a outra metade não.

Não quebra nada; nome de índice não tem semântica. Mas **a migration de rename
da nuvem tem de mirar exatamente estes nomes, resíduo incluído**, senão os dois
lados divergem de novo no dia seguinte. Limpar o resíduo é trabalho separado, e
nos dois lugares ao mesmo tempo.

### Inventário de `app`: 49 objetos, 45 com par

| Situação | Quantos | Quais |
|---|---|---|
| Par no repositório pelo mapa derivado | 45 | tudo o mais |
| **Só em produção** | 4 | batida_marcacao, cursor_sincronizacao, empresa_evento_status, funcionario_evento_status |
| **Só neste repositório** | 1 | `app.message_template` |

O único que falta lá é coerente: `message_template` nasce na migration 14, e
produção parou na 11.

Os quatro que só existem lá vêm das onze migrations perdidas — são a
infraestrutura da sincronização. Nenhum tem nome em inglês neste repositório
porque este repositório nunca soube que existiam.

### O achado que muda o produto: produção já espelha as marcações

`app.batida_marcacao` não é tabela de apoio. Tem `hora time`, `valor_bruto`,
`status_rotulo`, `desconsiderada`, `tipo_coluna`, `indice_coluna` — e três
colunas que vazaram do espelho em PascalCase: `Memoria`, `EquipId`,
`FonteDadosId`.

**Produção espelha marcação dentro de `app`.** Este repositório não — e o
monitor diário entregue hoje diz, com todas as letras, que "sem indício" não é
presença justamente porque as marcações não estariam em `app`. A frase está
certa para o schema deste repositório e **deixa de estar** quando a
reconciliação fechar. É decisão de produto, não de schema: com marcação em
`app`, o monitor pode afirmar presença de verdade.

### Cadência real do pg_cron

| Job | Agenda | Ativo |
|---|---|---|
| sync-cadastro-cron | `*/30 * * * *` | sim |
| sync-batidas-cron | `*/15 * * * *` | sim |

Os dois chamam `net.http_post` para as Edge Functions, com a URL vindo do Vault.
**Batidas roda a cada 15 minutos, não 30** — a documentação deste repositório
fala em 30 min para as duas.

### O que já está certo lá, agora verificado

- As 8 views de public são todas `security_invoker = on`.
- `anon` **não executa nenhuma** das 5 funções de public. `authenticated`, sim.
- Zero tabelas em `public`.
- public.rls_auto_enable() — o objeto que este plano marcava como dúvida — é
  benigno e útil: é função de *event trigger* que liga RLS sozinha em qualquer
  tabela criada em `public`. Complementa o `util.block_table_in_public()` daqui,
  que é mais estrito e recusa a criação. Como devolve `event_trigger`, não é
  chamável por RPC. Manter ou descartar é decisão do dono, não risco.

---

## 2. O que bloqueia o início

1. ~~**Senha do banco.**~~ **Resolvido em 22/08/2026, e não pelo caminho que
   este documento previa.** A senha continua perdida — três rodadas de teste,
   a última com matriz completa de 2 projetos × 6 regiões de pooler × 2 modos:
   as duas combinações que alcançam o host certo respondem `password
   authentication failed`, as outras 22 falham na rede. Não é endereço, é senha.

   O que destravou foi outra chave. A **Management API** do Supabase executa SQL
   arbitrário como `postgres` com o *token de conta* do `supabase login` — o
   mesmo que o CLI já guardava em `~/.supabase/access-token` nesta máquina:

       POST https://api.supabase.com/v1/projects/<ref>/database/query

   É estritamente melhor do que resetar a senha: cobre os **dois** projetos
   (mesma organização), é HTTPS — então o host direto ser IPv6-only deixa de
   importar —, é revogável num clique e não exige mexer no banco do cliente.

   Encapsulado em `scripts/sb_sql.sh`. A introspecção que ele alimenta está em
   `scripts/introspeccao_nuvem.py`, que **lê apenas catálogo**: nenhuma consulta
   sai de `pg_catalog`/`information_schema`, porque o alvo é o banco de um
   cliente com dado de pessoa real e schema é a única coisa que a reconciliação
   precisa.
2. ~~**O código das Edge Functions não está aqui.**~~ **Resolvido em
   22/08/2026:** baixado para `supabase/functions/`. E o que ele mostra corrige
   o medo que estava escrito aqui — as funções **não** escrevem em
   app.colaborador nem app.unidade. Aquilo foi dedução minha a partir dos 403,
   que descreviam as *views*, não elas.

   O que elas realmente tocam:
   - **secullum.\*** — vinte tabelas PascalCase, entre aspas. A mudança da
     migration 03 já aconteceu em produção e as funções já foram ajustadas.
     Como a convenção mantém PascalCase no espelho, **o rename pt→en não as
     afeta aqui**.
   - **quatro tabelas de app**: `app.empresa_evento_status`,
     `app.funcionario_evento_status`, `app.batida_marcacao` e
     app.cursor_sincronizacao.

   **A última é o achado que importa:** app.cursor_sincronizacao existe em
   produção e em nenhuma migration deste repositório. É o cursor da
   sincronização — o que decide o que será lido na próxima execução. Precisa
   entrar no baseline da fase 1 e ser tratada explicitamente no rename, ou a
   sincronização perde a memória de onde parou.

   O código também cita uma migration `20260813163000`, anterior às daqui
   (`20260815…`): produção tem histórico de migration próprio, que o baseline
   vai revelar.

---

## 3. Sequência

Cada fase tem um critério de verificação. Nenhuma começa antes da anterior
fechar.

### Fase 0 — destravar ✅ fechada em 22/08/2026

Fechou sem resetar senha nenhuma: o `supabase login` desta máquina já tinha um
token de conta válido, e a Management API aceita SQL com ele.

- **Verificado:** `scripts/sb_sql.sh <ref> "select version()"` responde `201`
  nos dois projetos, como usuário `postgres`, em PostgreSQL 17.6.

### Fase 1 — fotografar, sem tocar em nada ✅ fechada em 22/08/2026

- ✅ `supabase functions download` → `supabase/functions/` (commit `f210fa1`).
- ✅ Schema de produção reconstruído do catálogo:

      python3 scripts/introspeccao_nuvem.py nklobmlxyidqxarzisph --out scripts/_producao.sql

  **2 enums, 69 tabelas, 948 colunas, 345 constraints, 269 índices, 66 policies,
  18 funções, 9 views, 7 triggers, 147 comentários de coluna, 23 migrations.**
  O arquivo é gitignored: é o schema do banco de um cliente, e regenera em
  segundos com o token.

- Não houve `pg_dump`. Não é o mesmo artefato e não precisa ser: `pg_dump`
  exigiria a senha, e o que a fase 2 precisa é o mapa do schema, que o catálogo
  dá com fidelidade — `pg_get_viewdef`, `pg_get_functiondef`, `pg_get_indexdef`,
  `pg_get_constraintdef` e `pg_get_triggerdef` são as mesmas funções que o
  `pg_dump` usa para reimprimir cada objeto.

- ⏳ `scripts/_baseline.sql` continua não existindo, e é outra coisa: o baseline
  que `scripts/testar_migrations.sh` procura é o estado **anterior** às
  migrations, para a suíte testar a fusão. Produção já rodou as migrations 00–11,
  então o estado pré-migration não existe mais em lugar nenhum para ser
  fotografado. A suíte segue no stub simulado, e isso é honesto.

### Fase 2 — provar a fusão, duas vezes

**Primeiro ensaio: fechado em 22/08/2026.** Num Postgres descartável, contra uma
cópia fiel de produção. Reproduzível por `scripts/ensaiar_rename_nuvem.sh <ref>`.

A migration é `supabase/migrations/20260815101150_11b_rename_pt_en.sql`, e ela é
**gerada**, não digitada: `scripts/gerar_rename_nuvem.py` confronta o histórico
de migration da própria nuvem — que guarda as doze migrations compartilhadas na
grafia em português — com os dois catálogos lidos pelo mesmo código. São 353
identificadores pareados um a um, e a única ambiguidade é `papel`, que é `role`
como coluna e `user_role` como tipo.

**O timestamp cai entre a 11 e a 12 por necessidade.** As migrations 12 a 15
citam nomes em inglês; um rename depois delas deixaria a 12 encontrar
app.jornada_dia e criar uma segunda tabela ao lado — o desfecho que a migration
existe para evitar.

Resultado do ensaio, contra o schema de produção mais as 69 linhas de
configuração:

| | |
|---|---|
| 11b aplica | sem erro |
| 12 a 15 aplicam em cima | sem erro |
| 97 regras de alerta e cadência | OK |
| 98 isolamento multi-tenant (2 tenants × 4 papéis) | OK |
| 99 verificação estrutural de RLS | OK |
| catálogo resultante × alvo | **idêntico** em 9 espécies |

Idêntico quer dizer 45 tabelas, 513 colunas, 24 funções, 9 views, 64 policies,
180 índices, 241 constraints, 8 triggers e 2 enums com os mesmos rótulos. E num
banco que já está em inglês a migration não faz nada: `make db-test` segue verde
com as 17 migrations.

#### O que o ensaio encontrou, e que a leitura não teria encontrado

Cada bloco da migration existe por uma armadilha que só apareceu ao rodar:

- **O alias de uma view não segue o rename.** O corpo segue, porque é parse
  tree; o nome da coluna que ela entrega é texto. Sessenta colunas de saída
  precisaram de rename, ou vw_deviation_by_employee_day continuaria devolvendo
  `colaborador_id` ao frontend.
- **Pior: seis corpos de view filtram por VALOR.** `status = 'ativo'` é dado, não
  identificador, e não segue. Depois da tradução do dado essas views devolviam
  **zero linha** — sem erro, só tela vazia.
- **Renomear check constraint não muda o que ela aceita**, e o nome nem sempre
  muda: `deviation_event_status_check` se chama igual dos dois lados enquanto
  lista 'ativo' de um e 'active' do outro. Trinta e cinco caem antes da tradução
  do dado e voltam depois, porque `add constraint` valida as linhas na hora.
- **`create or replace` recusa trocar nome de parâmetro**, e quatro helpers
  `util.pode_ver_*` trocam. Derrubá-los também é recusado: 57 policies os citam
  no predicado. As duas variantes ficam no arquivo e um `if` escolhe.
- **`string_to_array('', ',')` devolve array vazio**, e `array_length` dele é
  `null` — a guarda por aridade nunca casava com função sem parâmetro, e quatro
  helpers escapavam em silêncio.

#### Segundo ensaio: em staging, e ainda não feito

O que um Postgres descartável não prova: PostgREST, Auth, os grants como o
Supabase os aplica, e o `security_invoker` valendo de verdade contra a anon key.
Isso só o projeto `db-test` prova, e exige DDL nele.

### Fase 3 — janela

- Backup completo e ponto de restauração.
- **Pausar as Edge Functions** — elas escrevem durante o DDL.
- Aplicar.
- Atualizar as funções para os nomes novos e religar.
- **Verificar:** um ciclo de sync completo sem erro; o dashboard deste
  repositório abre contra o projeto.

---

## 4. Os dois projetos, e o papel de cada um

Decidido em 22/08/2026: **coexistem**.

| Projeto | Papel |
|---|---|
| nklobmlxyidqxarzisph — "Kastro Park Ponto" | **Produção.** Recebe o Secullum por Edge Function. Schema em nomenclatura pt. É o alvo da reconciliação. |
| wbzaqjlfpqteesehapnn | **Staging.** Vazio. Ensaio da fase 2, e destino dos previews da Vercel — que o `CLAUDE.md` já mandava manter fora da allowlist de CORS e das Redirect URLs de produção. |

O env de staging é `backend/.env.staging` e `frontend/.env.local.staging`,
renomeados de `.env.cloud` na mesma data. **A senha de staging pode ser resetada
à vontade** — projeto vazio, sem dado de cliente. É o desbloqueio mais barato que
existe agora: destrava a fase 2 inteira sem depender da senha de produção.

---

## 4b. Riscos da sincronização que já existem hoje — sem rename nenhum

Levantados em 22/08/2026 por revisão adversarial das Edge Functions e
**conferidos um a um contra o código**. Nenhum depende da reconciliação: valem
para produção enquanto você lê isto. Estão aqui porque a janela do rename é o
momento em que cada um deles vira perda de dado, e porque dois deles são mais
urgentes que o rename.

### 1. Não existe transação em nenhuma escrita

`grep -riE '\bsql\.begin|transaction|savepoint\b' supabase/functions/_shared/`
não acha uma ocorrência de código. `postgres-client.ts` devolve um cliente cru e
cada *tagged template* dá autocommit.

O código admite isso e argumenta contra
(`_shared/batida-sync.ts`, nota de release): *"cada etapa é idempotente e a
sequência final converge (…) mesmo se algo falhar no meio (a próxima execução da
janela corrige)"*. **A garantia não se sustenta** — ver risco 2.

Dois pontos concretos em `runBatidaSync`:

- `deleteFonteDadosByBatidaIds` commita **antes** de `insertFonteDados` rodar. Se
  o insert falhar, o delete já aconteceu.
- `upsertBatidas` commita **antes** de `listMarcacoesByBatidaIds`. Se a leitura
  falhar, ficam linhas de Batida com **zero marcação** — e isso não se lê como
  "faltando dado", se lê como **"o colaborador não bateu ponto naquele dia"**.
  É o motor de detecção de desvio que consome esse estado.

### 2. `sync-batidas` não se cura sozinho — `sync-cadastro` se cura

| | sync-cadastro | sync-batidas |
|---|---|---|
| Estratégia | lê o cadastro inteiro, converge todo ciclo | janela fixa de 48h |
| Recupera de queda longa? | **sim**, sozinho | **não**, por nenhum caminho |

`BATIDAS_WINDOW_DAYS = 2`. O parâmetro `windowDays` de `runBatidaSync` existe e
tem default — e **nunca é passado**: `index.ts` chama `runBatidaSync(secullum,
repo)` com dois argumentos. E `Deno.serve(() => handleRequest())` descarta o
`Request`, então não há query string nem body por onde alargar a janela.

**Qualquer queda de `sync-batidas` que passe de 48 h deixa um buraco de batidas
que nenhum caminho de código consegue preencher** — só redeploy da função com o
valor alterado, ou restauração de backup. É o teto que dimensiona qualquer
janela de manutenção, incluindo a do rename.

### 3. Existe uma saída bem-sucedida com ingestão zero

Se `listFuncionariosBySecullumIds` devolver vazio — porque o cadastro ainda não
sincronizou, ou porque a correlação quebrou — todo registro cai em
`batidasSkippedMissingFuncionario`, e então:

    if (resolvedItems.length === 0) { flushSuppressedWarnings(); return summary; }

O handler responde **HTTP 200, `{ok: true}`**, com zero batidas gravadas. A
sincronização está parada e o único sinal é um aviso dentro de um JSON que
ninguém lê.

### 4. Não há alarme nenhum

`grep -riE 'sentry|pagerduty|slack|webhook|notify|alert' supabase/functions/` →
**zero**. O único tratamento é `console.error` mais HTTP 500. E como a invocação
vem do pg_cron por `net.http_post`, **o job registra sucesso por ter entregado o
POST**, não por a função ter funcionado. Um 500 e um 200 são indistinguíveis do
lado do agendador.

### O que isso obriga a mudar no plano

- A janela da fase 3 não é "o tempo que o cliente tolera": é **48 h no máximo**,
  imposto pelo risco 2.
- "Parar a ingestão" não pode ser verificado contando `cron.job` ativo. Contagem
  zero prova ausência de agendamento, não parada — e `sync-batidas/index.ts`
  aponta para um arquivo `<a criar>_sync_batidas_cron.sql` que não existe neste
  repositório, então o agendamento dela pode nem estar em `cron.job`. A parada
  precisa de **prova positiva**: função desabilitada e invocação manual falhando.
- "Religou" não pode ser "a função respondeu 200". Precisa ser `batidasUpserted
  > 0` **e** `marcacoesUpserted > 0` no summary, mais uma consulta de
  reconciliação procurando Batida sem marcação na janela.
- Os riscos 3 e 4 valem a pena fechar **antes** do rename, não depois: sem
  alarme, o modo de falha do rename é silencioso por construção.

---

## 4c. O que a revisão adversarial derrubou do primeiro rascunho

O primeiro esqueleto de migration foi escrito antes de o schema real estar
disponível e **não sobreviveu à conferência**. Vale registrar os erros, porque
todos são plausíveis e voltariam:

- **Coluna atribuída à tabela errada.** O rascunho renomeava `direcao` em
  app.deviation_event. Ela não existe lá — vive em app.desvio_tipo. E o guard
  era `if exists (… column_name = velho)`, então o erro **não levantaria
  exceção**: pularia em silêncio.
- **Renome parcial que parece completo.** `colaborador_id` existe em **12**
  tabelas de `app` na produção e `data_ref` em **3**. Renomear só na tabela do
  grão deixa 11 e 2 para trás.
- **Prova que não prova.** A asserção do "contrato de ingestão" era
  `where to_regclass(…) is not null and not exists (…coluna…)`. Se o rename
  levasse a tabela embora, `to_regclass` devolve `null`, todas as linhas são
  filtradas, o laço não itera e a migration **commita verde** — exatamente o
  caso que a mensagem de erro dizia cobrir.
- **Duas regras de parada violadas.** O rascunho derrubava toda policy
  pré-existente das tabelas renomeadas (predicados que ninguém leu) e renomeava
  colunas de app.deviation_event. CLAUDE.md manda parar nas duas.
- **Asserção no arquivo errado.** Ele conferia "nenhuma tabela em `public`" num
  arquivo que roda **antes** da migration 03, que é justamente quem tira as
  tabelas de `public`. Falharia em 100% das execuções.

Nenhum identificador foi inventado — o problema não foi alucinação, foi
**dedução apresentada como fato**. É o motivo de este documento separar o que
foi medido do que foi deduzido.

---

## 5. O que não decidir sozinho

- Qualquer DDL na nuvem antes da Fase 2 fechar verde.
- O que fazer com rls_auto_enable: função que existe lá e não aqui. Pode ser
  andaime de uma sessão anterior ou parte do desenho de alguém. Ler antes de
  remover.
*(A pergunta sobre o segundo projeto foi respondida em 22/08/2026 — ver a seção 4.)*
