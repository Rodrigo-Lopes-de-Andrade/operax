# CLAUDE.md

**Projeto:** OperaX
**Descrição:** Camada de gestão, automação e inteligência sobre sistemas de ponto — lê o Secullum, detecta desvio de jornada, avisa o gestor no dia e consolida custo de pessoal. Multi-tenant e **white-label**: FastPark é o cliente âncora e a marca que aparece na interface. "OperaX" é o nome do produto no repositório, nos identificadores e nestes documentos — não aparece em nenhuma superfície.
**Stack:** Next.js 16 (React 19) + FastAPI (gerenciado com `uv`) · Agente LangChain 1.x (`create_agent`) · Supabase (PostgreSQL + Auth + Storage; migrações com Supabase CLI) · Deploy: Railway (backend) / Vercel (frontend)

---

## Diretrizes de Comportamento

Este projeto prioriza a **correção sobre a velocidade**. Ao interagir com o código, siga rigorosamente as diretrizes abaixo. Para tarefas triviais, use o bom senso.

### 1. Pense Antes de Codificar

Não assuma. Não esconda incertezas. Exponha tradeoffs.

- **Premissas:** Declare explicitamente. Prossiga com a interpretação mais razoável e registre a premissa — não pare por micro-dúvidas.
- **Quando parar e perguntar:** Só interrompa quando a decisão for **irreversível, custosa, ou alterar interface pública / schema / contrato de API**. Para o resto, escolha a opção mais simples, declare a premissa e siga.
- **Interpretações:** Se houver múltiplas abordagens de peso semelhante, apresente-as e siga com a mais simples — só aguarde resposta se o caso cair na regra de parada acima.
- **Claridade:** Se o requisito for ambíguo _e_ a escolha errada for cara de reverter, pare e nomeie exatamente o que causa confusão. _Ex: "esse desvio conta como faltante ou é só informativo? muda o KPI e o ranking"._
- **Neste projeto, três coisas sempre param:** mudança em policy de RLS, exposição de coluna nova numa view de `public`, e qualquer alteração no grão de `app.deviation_event`.

### 2. Simplicidade Primeiro

Implemente o mínimo necessário para resolver o problema.

- **Escopo:** Não adicione funcionalidades, abstrações para uso único, flexibilidade extra ou "configurabilidade" não solicitada. _Ex: não crie interface/factory para algo com uma única implementação._
- **Robustez:** Evite tratamento de erro para cenários impossíveis. _Ex: não valide `None` num valor que o tipo já garante existir._
- **Refatoração:** Se o código que você está escrevendo ou alterando **nesta tarefa** puder ser reduzido, reescreva-o — esta regra não autoriza refatorar código fora do escopo (ver seção 3).
- **Teste de Senioridade:** Pergunte-se: "Um engenheiro sênior consideraria isso sobre-engenheirado?". Se sim, simplifique.
- **Exceção deliberada:** o modelo de dados de segurança (schemas isolados, PII apartada, três eixos de autorização) parece sobre-engenheirado e não é. Não simplifique.

### 3. Mudanças Cirúrgicas

Altere apenas o necessário. Limpe apenas a bagunça que você criou.

- **Edição:** Não "melhore" código adjacente, comentários ou formatação. Não refatore o que não está quebrado.
- **Estilo:** Siga o estilo existente, mesmo que não seja a sua preferência.
- **Código Morto:** Se encontrar código morto não relacionado, mencione-o, mas não delete.
- **Órfãos:** Remova apenas imports/variáveis/funções que suas alterações tornaram inúteis.
- **Rastreabilidade:** Cada linha alterada deve ter justificativa direta no pedido do usuário.

### 4. Execução Orientada a Objetivos

Defina critérios de sucesso antes de começar. Itere até a verificação.

- **Critérios:** Transforme tarefas vagas em metas verificáveis.
  - Bug: Escrever teste que reproduz → Fazer passar.
  - Motor de detecção: Escrever caso com batidas reais e resultado esperado → Fazer passar.
  - Segurança: Escrever asserção em `scripts/98_teste_isolamento_tenant.sql` → Fazer passar.
- **Planejamento:** Para tarefas complexas, declare um plano breve:
  1. `[Passo]` → verificar: `[Critério]`
  2. `[Passo]` → verificar: `[Critério]`
- **Definição de concluído:** Rode `make test && make lint` antes de declarar a tarefa concluída. Se falhar, corrija **antes** de reportar — não entregue com testes vermelhos. Se tocou banco, `make db-test` também.

---

## Stack

Convenções não-óbvias (o resto está em `package.json` / `pyproject.toml`):

### Backend (`backend/`)

- FastAPI servindo três coisas: API do painel para dado individual e sensível, o assistente de IA, e os endpoints administrativos. Motor e sender rodam agendados no mesmo container. **A sincronização não** — ver abaixo.
- Agente LangChain 1.x com `create_agent` — multi-provider (OpenAI / Anthropic / Google GenAI). **Sem text-to-SQL:** o agente escolhe do catálogo `app.metric` e devolve `{metrica, parametros}`; quem executa é o backend, como o usuário que perguntou.
- **A sincronização com o Secullum não é worker Python.** `backend/operax/sync/` **não existe e não deve ser criado**. A regra que continua valendo é a que importa: trocar de sistema de ponto mexe num lugar só.
  ⛔ **Mas esse lugar não é mais a Edge Function — e o repositório não tem o código dele.** Medido em produção em 27/08/2026: `GET /v1/projects/<ref>/functions` devolve `[]`, e os dois jobs de `pg_cron` chamam o serviço **`kastropark-jobs` na Vercel**, com a URL vinda dos segredos `vercel_jobs_base_url` e `vercel_cron_secret` do Vault. A troca aconteceu em 25/08, uma hora depois de o P1 blindar as Edge Functions.
  Então: `supabase/functions/` (Deno: `sync-cadastro`, `sync-batidas`, `secullum-test-auth`) é **o runner deste repositório**, não o de produção. Afirmação sobre risco fechado ali **não vale para produção** — ver `docs/PLANO-RECONCILIACAO-NUVEM.md` e `docs/INCIDENTE-2026-08-27-EXPOSED-SCHEMAS.md`.
  ✅ **Decisão do dono, 28/08/2026: isso tem prazo de validade.** A janela de convergência **substitui** o `kastropark-jobs` por estas Edge Functions, e o código da Vercel não será lido — ele não vai continuar. Enquanto a janela não acontece, tudo acima continua valendo: quem escreve em produção hoje ainda é a Vercel. O passo 4 do `docs/RUNBOOK-JANELA-CONVERGENCIA.md` tem os pré-requisitos. O reset da senha do banco, que era o mais demorado, **foi feito em 28/08** — as funções conectam direto e exigem `DATABASE_URL`, que já é secret delas.
  E há uma diferença já provada, na marra: o `kastropark-jobs` fala com o banco **por PostgREST**, enquanto as Edge Functions deste repo usam conexão direta. Foi o que derrubou a sync em 27/08.
  A origem autentica com usuário, senha, `client_id` e `bank_id` (secrets `SECULLUM_USERNAME`, `SECULLUM_PASSWORD`, `SECULLUM_CLIENT_ID`, `SECULLUM_BANK_ID`). ✅ **Medido em 31/08/2026** pela Management API (só nomes, nunca valores): os três primeiros e o `DATABASE_URL` **já estão** configurados como secrets das Edge Functions de produção. O `SECULLUM_BANK_ID` não está lá, e **é inofensivo nesta conta**: o código o declara opcional e cai em `banks[0]`, e a conta tem um banco só (`88727`) — medido em 31/08 publicando a `secullum-test-auth` em produção, que voltou `ok: true`. **As credenciais do Secullum em produção funcionam.** ⚠️ A sincronização passa a depender de a lista ter um elemento só: uma segunda empresa na conta do Secullum muda `banks[0]` sem avisar.
- Motor de detecção conforme `docs/SPEC-TECNICA.md` §3. Roda em `modo='sombra'` até o falso positivo cair abaixo de 5%.
- Sender de alertas consome `app.alert_queue` com `for update skip locked`. **O motor nunca envia** — enfileira.
- Streaming SSE real para as respostas do assistente.
- Acesso ao Postgres por conexão direta (`psycopg`) com `search_path` por schema; PostgREST só para o que vem do navegador.
- Projeto Python gerenciado com `uv` (`pyproject.toml` + `uv.lock`). O frontend segue com `npm`.

### Banco (`supabase/`)

Fronteira de segurança do produto inteiro. Detalhe em `docs/DICIONARIO-DE-DADOS.md` (gerado, não editar à mão).

| Schema | Conteúdo | Exposto ao PostgREST |
|---|---|---|
| `secullum` | Espelho literal da origem, PascalCase, PII completa | **Não** |
| `app` | Domínio OperaX, snake_case, RLS obrigatória | **Não** |
| `util` | Helpers `security definer` das policies | **Não** |
| `public` | Só views (`security_invoker = on`) e RPCs | **Sim, e só ele** |

- Migrações com Supabase CLI (`supabase migration new`). **Não há Alembic neste projeto.**
- Usuários vivem em `auth.users`, gerenciado pelo Supabase Auth — não escrever migration para essa tabela.
- Event trigger bloqueia `CREATE TABLE` em `public`. Se ela disparar, o schema escolhido está errado, não a trigger.
- `app.mv_deviation_day` é materialized view: **não respeita RLS**, contém todos os tenants, nunca é exposta.

### Frontend (`frontend/`)

- Next.js 16 com App Router e React 19.
- Tailwind CSS v4 (config CSS-first via `@theme` no CSS global; PostCSS com `@tailwindcss/postcss`). **Não** aplicar padrões v3: sem `tailwind.config.ts`, sem `@tailwind base/components/utilities`.
- Dois caminhos de dado — ver Contrato.
- Estado de filtro vive na **query string**, não em estado local: o link do relatório de WhatsApp abre o dashboard já filtrado.
- Gráficos com Recharts. Sem realtime na v1 — os dados só mudam quando o worker roda.

### Qualidade

- Ruff (Python), Prettier + TS strict (frontend). Sentry para erros da aplicação.
- Observabilidade do agente: **LangSmith é o default** (traces de LLM, tools, latência e tokens). Não introduzir outro vendor sem decisão explícita.
- Testes: pytest (backend), Vitest (frontend), Playwright (E2E).
- **Suíte de banco** (`make db-test`): sobe Postgres descartável, aplica as 36 migrations, roda 23 asserções funcionais de isolamento (dois tenants, quatro papéis), 24 asserções de regra de alerta, cadência e provedor, e 13 verificações estruturais, regenera o dicionário de dados, valida que toda referência a objeto de banco na documentação existe e **confere o espelho do Secullum contra a captura de produção**. Obrigatória em qualquer PR que toque policy, view, grant ou migration.

### Deploy

- **Backend:** Railway, serviço `operax-api`, deploy automático a cada push em `feature/s5-gestao-de-ponto`, root `/backend`. ⚠️ **Medido em 01/09/2026:** o builder configurado é **RAILPACK**, não o `Dockerfile`, e **não existe pre-deploy command** — ao contrário do que esta linha afirmava. **Nenhum deploy aplica migration alguma**, em nenhum ambiente. Quem quiser schema novo aplica à mão, e é por isso que staging está sem a `33`.
- **Frontend:** Vercel.
- **Banco:** Supabase gerenciado. **Exposed schemas deve conter apenas `public` e `graphql_public`** — checar após qualquer mudança de projeto.
- **Topologia:** instância única no Railway — rate limiting in-memory é aceitável; revisar antes de escalar horizontalmente.
- **Env de produção:** painéis do Railway e da Vercel; chave nova entra no `.env.example` **e** no painel correspondente. Credencial de integração por tenant **não** é env — vai para o Supabase Vault.
- **Operação:** logs via `railway logs` e painel da Vercel; rollback = redeploy de versão anterior. Health check em `GET /health`.
- **Previews da Vercel:** por padrão **fora** da allowlist de CORS e das Redirect URLs do Supabase Auth. O projeto de staging existe e é o destino deles — `wbzaqjlfpqteesehapnn`, env em `backend/.env.staging`. Produção é `nklobmlxyidqxarzisph` ("Kastro Park Ponto"), que recebe o Secullum e ainda não conversa com este repositório: ver `docs/PLANO-RECONCILIACAO-NUVEM.md`.

---

## Mapa de Arquitetura

- **`supabase/functions/`** — o espelhamento da origem, em Edge Functions do Supabase (Deno): `sync-cadastro`, `sync-batidas`, `secullum-test-auth`. Trocar de sistema de ponto acontece só ali. Versionadas aqui desde o commit `f210fa1`. Cadência oficial: **batidas a cada 15 min, cadastro a cada 30** — ver `docs/DECISAO-CADENCIA-SYNC.md`.
- **`backend/operax/motor/`** — `cadastro.py` promove empresa, departamento e colaborador do espelho para o domínio e devolve a **fila de mapeamento pendente** (empresa vem de `Funcionario.empresa_id`, nunca do departamento — regra 5); `regras.py` = o SQL do que é desvio num dia, sem driver e sem cópia, lido pelos três statements e pelo `make db-test`; `jornada.py` materializa `app.expected_workday` com grau de confiança (é onde o 12x36 é tratado); `deteccao.py` grava `app.deviation_event` com `on conflict` por (colaborador, dia, tipo, modo); `revogacao.py` revoga o que sumiu e substitui o que já saiu em relatório. `python -m operax.motor` roda os três em ordem.
- **`backend/operax/alertas/`** — `ciclo.py` monta `app.report_cycle` com reserva transacional (`report_cycle_id is null` é a cláusula inteira do "um desvio em exatamente um ciclo"); `outbox.py` enfileira com chave de idempotência; `sender.py` consome com `for update skip locked` e **pergunta o gate G4 ao banco** — sem execução do motor em produção, nada é entregue. `provedores/` = WhatsApp e e-mail atrás de uma interface **template-first**: `enviar(template, variaveis, destino)`, nunca string pronta — ver `docs/DECISAO-WHATSAPP.md`.
- **`backend/operax/agente/`** — `catalogo.py` = carrega `app.metric`, filtra por domínio **antes** de o modelo ver, valida a escolha com **cinco** recusas nomeadas (a quinta confere o *valor*, não só o nome do parâmetro) e monta a consulta (o `BINDINGS` é o único lugar em que nome de coluna encosta em SQL); `executor.py` = roda a métrica **como o usuário**, sob `user_scope`; `agente.py` = o `create_agent`, a allowlist de modelo e o turno como eventos tipados — o modelo tem **duas** ferramentas, consultar e recusar, e nenhuma outra forma de alcançar dado; `e2e.py` = o provider falso de `E2E_FAKE_LLM`, que passa pela mesma fronteira.
- **`backend/operax/rh/`** — `ownership.py` = a matriz dono-do-campo (sync x RH), lida por template, tela e import; `validators.py` = um funil só para formulário e planilha; `templates.py` = o que cada modelo `.xlsx` carrega; `workbook.py` = gera e lê o arquivo; `importer.py` = o veredito por linha, sem escrever; `repository.py` = o SQL, com leitura como o usuário e gravação junto da auditoria; `employees.py` = a lista e o detalhe da aba Colaboradores; `carga_inicial.py` = o conversor de implantação, que preenche os modelos baixados e **não abre conexão com o banco**.
- **`backend/operax/core/`** — `db.py` = pools por schema; `tenant.py` = contexto de tenant (todo acesso com `service_role` passa por aqui); `config.py`; `vault.py` = leitura de credencial por tenant.
- **`backend/server/`** — `main.py` = entrypoint; `deps.py` = valida o JWT do Supabase e resolve tenant e papel; `models.py` = **fonte da verdade dos schemas**; `routers/` = endpoints por área.
- **`supabase/fixtures/`** — `espelho_secullum.sql` = o schema `secullum` como **produção** o tem, capturado do catálogo em 01/09/2026. As 22 tabelas do espelho são desenho da outra equipe: nenhuma migration daqui as cria. Vinte chegam ao ensaio pelo `scripts/_baseline.sql` (em `public`, a 03 as varre); as duas snake_case pela fixture, porque a 03 só varre `^[A-Z]`. ⚠️ **A captura sozinha já existia e mentia** — estava três linhas atrás de produção, e as três eram `"Estrutura".departamento_id`, a coluna que bloqueou a troca do runner. O que vale é a conferência: `scripts/verificar_espelho.py` roda no `make db-test` (ensaio contra a fixture, sem rede) e sob demanda contra produção (`python3 scripts/verificar_espelho.py <ref>`), que é obrigatório antes de marcar janela.
- **`supabase/migrations/`** — 36 migrations aplicadas em ordem (numeradas 00–34, com a 11b). Ver `docs/PLANO-BANCO-OPERAX.md`. ✅ **Produção está convergida desde 31/08**: a janela aplicou as 22 que faltavam e a `33` consertou uma regressão delas — ledger em 46 (23 registros antigos + 22 + 1). Quando um documento antigo fala em "as 22", é do lote da janela que ele fala, não do total. ⚠️ **A `34` é a exceção e ainda não está lá**: ela dá o lock de sobreposição a `app.sync_run` e é **pré-requisito do deploy das Edge Functions** — sem o índice, a reivindicação estoura e a sincronização não roda. Ver `docs/RUNBOOK-JANELA-CONVERGENCIA.md`, passo 7, item 5.
- **`scripts/`** — diagnóstico, testes de isolamento, gerador do dicionário, verificador de documentação.
- **`frontend/src/`** — `app/` roteamento; `components/` (`ui/` = design system); `lib/supabase.ts` = cliente com anon key; `lib/api.ts` = cliente do FastAPI; `state/` = sessão + streaming do assistente.

### Estrutura de pastas (manter sempre que possível)

```
.
├── backend/
│   ├── operax/
│   │   ├── motor/
│   │   │   ├── jornada.py
│   │   │   ├── deteccao.py
│   │   │   └── revogacao.py
│   │   ├── alertas/
│   │   │   ├── provedores/
│   │   │   ├── ciclo.py
│   │   │   ├── outbox.py
│   │   │   └── sender.py
│   │   ├── agente/
│   │   │   ├── agente.py
│   │   │   ├── catalogo.py
│   │   │   └── executor.py
│   │   ├── rh/
│   │   │   ├── ownership.py
│   │   │   ├── validators.py
│   │   │   ├── templates.py
│   │   │   ├── workbook.py
│   │   │   ├── importer.py
│   │   │   ├── repository.py
│   │   │   ├── employees.py
│   │   │   └── carga_inicial.py
│   │   └── core/
│   │       ├── config.py
│   │       ├── db.py
│   │       ├── storage.py
│   │       ├── tenant.py
│   │       └── vault.py
│   ├── server/
│   │   ├── routers/
│   │   ├── deps.py
│   │   ├── main.py
│   │   └── models.py
│   ├── tests/
│   ├── .env.example
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── state/
│   ├── e2e/
│   ├── .env.local.example
│   ├── next.config.mjs
│   ├── package.json
│   ├── playwright.config.ts
│   ├── postcss.config.mjs
│   ├── tsconfig.json
│   └── vitest.config.ts
├── supabase/
│   ├── migrations/
│   ├── fixtures/           # espelho_secullum.sql = o schema `secullum` de producao
│   ├── functions/          # sincronizacao com o Secullum (Deno) — ainda nao baixadas
│   └── config.toml
├── scripts/
│   ├── 00_diagnostico.sql
│   ├── 88_teste_espelho.sql
│   ├── 98_teste_isolamento_tenant.sql
│   ├── 99_verificacao_rls.sql
│   ├── gerar_dicionario.py
│   ├── rh_carga_inicial.py
│   ├── testar_migrations.sh
│   ├── verificar_docs.py
│   └── verificar_espelho.py
├── docs/
├── CLAUDE.md
├── Makefile
└── docker-compose.yml
```

---

## Contrato Front ↔ Back

Ponto de maior acoplamento — trate com cuidado. Neste projeto há **dois caminhos**,
e escolher o errado é uma falha de segurança, não de estilo.

### Caminho 1 — navegador direto no Supabase (anon key)

Só agregado não sensível: `vw_deviation_summary_by_unit`, `vw_deviation_daily_trend`,
`vw_deviation_by_employee_day`, `vw_unit`, `vw_employee`, e as RPCs
`fn_kpi_period`, `fn_ranking_by_unit`, `fn_ranking_by_employee`, `fn_recurrence`.

- A RLS filtra por tenant e escopo automaticamente. **O cliente nunca envia
  `tenant_id`** — e não adianta enviar: a policy não confia em parâmetro do cliente.
- `anon` não lê nada. A sessão precisa estar autenticada.

### Caminho 2 — navegador → FastAPI (dado individual, sensível ou escrita)

- **`service_role` vive somente no backend FastAPI.** Nunca no Next.js, nunca no
  navegador, nunca numa route handler da Vercel. Uma única chave-mestra, num
  único lugar.
- `service_role` **ignora RLS**. Todo acesso passa por `operax/core/tenant.py`,
  que exige o tenant resolvido do token. Consulta sem filtro de `tenant_id` é bug
  de segurança, não descuido.
- O backend revalida o papel e o domínio sensível antes de responder — não confia
  no que o frontend diz que o usuário pode ver.

### Autenticação

- Supabase Auth. O access token do Supabase é o **mesmo** nos dois caminhos: vai
  no header `Authorization: Bearer <token>` para o FastAPI, que o valida contra o
  JWKS do projeto Supabase. Não existe JWT próprio nem tabela de usuários própria.
- Sessão gerenciada pelo `@supabase/ssr`; refresh é responsabilidade do SDK.
- **Domínios (produção):** frontend em `app.<dominio>` (Vercel) e API em
  `api.<dominio>` (Railway) — mesmo domínio raiz.
  ⚠️ **O desenho ainda não é o que está no ar.** Medido em 01/09/2026: o painel
  vive em **`app.fastparks.com.br`** (`operaxfonted.vercel.app` redireciona 307
  para lá), mas **`api.fastparks.com.br` não resolve** — o painel chama a API
  pelo endereço do Railway. E o painel aponta ponta a ponta para **staging**,
  não para produção. Ver `docs/RUNBOOK-JANELA-CONVERGENCIA.md`.
- **CORS:** origem exata do frontend com `allow_credentials=True`. Com credenciais,
  `*` é proibido.

### Assistente de IA

- **Endpoint:** `POST /assistente/perguntar`, streaming SSE.
- **Transporte:** SSE consumido via `fetch` + `ReadableStream` — **não** usar
  `EventSource` nativo (não aceita header `Authorization`).
- **Eventos:**
  - `event: token` · `data: {"content": "…"}` — delta de texto.
  - `event: metrica` · `data: {"codigo": "…", "titulo": "…", "parametros": {…},
    "ignorados": […], "linhas": N}` — qual métrica foi escolhida; a UI mostra
    período e filtros para o usuário conferir.
    `parametros` traz só o que **de fato** filtrou; `ignorados` traz o que a
    métrica não filtra e por isso foi descartado — um filtro pedido e não
    aplicado é a diferença entre o número certo e a frase errada.
  - `event: recusa` · `data: {"codigo": "…", "motivo": "…"}` — fora do catálogo,
    sem permissão de domínio, parâmetro ou valor que a métrica não aceita, ou o
    modelo declarando que nenhuma métrica serve (`sem_metrica`). **Recusa é
    resposta válida**, não erro: ela chega dentro de um 200.
  - `event: error` · `data: {"message": "…"}` — erro mid-stream; encerra o turno.
  - `event: done` · `data: {"consulta_id": "…", "modelo": "…",
    "tokens_entrada": N, "tokens_saida": N, "latencia_ms": N}` — quem pergunta é
    quem gasta, então o custo do turno volta com ele.
  - `event: ping` a cada ~15 s — keep-alive; sem ele proxies derrubam o stream.
- A rota SSE fica **fora** de compressão e buffering.
- **Erros fora do stream:** status ≠ 2xx antes do primeiro byte (401/403/429)
  retorna o JSON padrão FastAPI (`{"detail": …}`); o cliente checa `res.ok`
  **antes** de começar a ler o stream.

### Fonte da verdade

Schemas Pydantic em `backend/server/models.py`. Tipos do frontend gerados a partir
do banco com `supabase gen types typescript` — não escrever tipo de tabela à mão.

### Validação server-side (multi-tenant)

- `thread`/consulta/ocorrência: ownership validado contra o tenant do token.
- Modelo de LLM solicitado validado contra allowlist em `backend/operax/agente/` —
  nunca aceitar id arbitrário do cliente.
- `POST /assistente/perguntar` tem rate limiting por usuário — LLM pago sem limite
  é abuso de custo trivial.
- **Adicionar métrica ao assistente:** inserir em `app.metric` **e** garantir que
  a view/RPC alvo existe — sempre no mesmo PR, com `make db-test` verde.

---

## Setup e Execução

```bash
# 1. Dependências (subshells: cada linha roda a partir da raiz do repo)
(cd backend && uv sync)
(cd frontend && npm install)

# 2. Ambiente
cp backend/.env.example backend/.env              # preencha as chaves
cp frontend/.env.local.example frontend/.env.local

# 3. Banco local + migrações
supabase start                                    # Postgres + Auth + Storage locais
supabase db reset                                 # aplica as 36 migrations do zero

# 4. Rodar / verificar
make dev                    # backend + frontend
make dev-backend            # só a API (uv run uvicorn ...)
make dev-frontend           # só a UI
make test && make lint      # obrigatório antes de concluir
make db-test                # obrigatório se tocou banco, policy, view ou grant
make e2e                    # Playwright — fora do gate acima
make build                  # build de produção

# Tarefas do worker (rodam sob demanda em dev)
make sync                   # espelha a source
make motor MODO=sombra      # detecção sem publicar
make motor MODO=producao    # só depois do gate de falso positivo
make sender                 # consome a fila de alertas

# Testes pontuais (iteração rápida — não rode a suíte inteira a cada ciclo)
(cd backend && uv run pytest tests/test_motor.py -k nome_do_teste)
(cd frontend && npx vitest run src/caminho/arquivo.test.tsx)
(cd frontend && npx playwright test e2e/fluxo.spec.ts)
```

**Variáveis de ambiente** (nunca commitar nenhuma):

- **Backend — obrigatórias:** `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_JWKS_URL`, e **pelo menos uma** chave de provider (`OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | `GOOGLE_API_KEY`).
- **Backend — opcionais:** demais chaves de provider, `SENTRY_DSN`, `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` (+ `LANGSMITH_PROJECT`), `CORS_ORIGINS` (origens exatas do painel, separadas por vírgula; default `http://localhost:3000`; `*` é rejeitado no startup porque a API responde com credenciais).
- **Credencial do Secullum:** hoje são secrets da Edge Function, no escopo do **projeto** — não por tenant. Funciona com um cliente e quebra no segundo, que é o desenho que `app.integration_secret` + Vault previa. Decisão pendente antes do segundo tenant.
- **Não são env:** token do provedor de WhatsApp — seja ele `meta_cloud` (token da WABA), `z_api` ou `uazapi` (token da instância). São **por tenant** e vivem no Supabase Vault, referenciadas em `app.integration_secret`. Um tenant tem no máximo um provedor de WhatsApp ativo, garantido por índice único.
- **Frontend:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL` e, se usado, `NEXT_PUBLIC_SENTRY_DSN`.

---

## O que NÃO tocar

- **Migrations já aplicadas** (`supabase/migrations/`) — nunca edite; crie uma nova com `supabase migration new`.
- **`docs/DICIONARIO-DE-DADOS.md`** — gerado por `scripts/gerar_dicionario.py`. Editar à mão faz a documentação divergir do schema silenciosamente.
- **`auth.*` e `storage.*`** — gerenciados pelo Supabase.
- **Asserções da suíte de isolamento** — se `scripts/98_*.sql` ou `scripts/99_*.sql` ficar vermelho, corrija o código, não o teste.
- **Segredos e `.env`** — nunca commitar chaves.

---

## Convenções

- **Backend:** Ruff (lint + format), type hints obrigatórios, Pydantic v2, pytest. Dependências via `uv` (não usar `pip install` direto). Schema do banco via Supabase CLI (nunca `CREATE TABLE` manual, nunca Alembic).
- **Frontend:** Prettier + TypeScript strict (`tsc --noEmit` no `make lint`), validação com Zod, forms via React Hook Form. Vitest para componentes; Playwright para login, dashboard filtrado e assistente.
- **SQL:** toda migration é idempotente (`if not exists`, `drop policy if exists`) e termina com um bloco `do $$` que **falha alto** se a garantia dela não se sustentar. Siga o padrão das 15 existentes.
- **E2E:** Playwright sobe front+back com provider de LLM **fake** (`E2E_FAKE_LLM=1`) e projeto Supabase local. Roda com `make e2e`, fora do gate `make test`.
- **Idioma:** código, identificadores, commits e comentários em inglês; UI e textos ao usuário em pt-BR. O domínio segue inglês snake_case, alinhado com `work_schedule_day`, que já existia antes deste modelo. O mapa completo pt→en está em `scripts/rename_map.py` — consultar antes de nomear qualquer coisa nova.
- **Exceção deliberada:** identificadores brasileiros que são nome próprio de instrumento legal permanecem sem tradução — `cnpj`, `cpf`, `rg`, `pis`, `ctps`, `fgts`, `inss`, `irrf`, `rat`, `aso`. "CNPJ" virar `tax_id` perde informação em vez de ganhar, do mesmo jeito que ninguém traduz "IBAN".
- **Vocabulário de negócio em inglês:** *deviation*, não *desvio*, em nome de objeto. Na UI em pt-BR continua sendo "desvio" e "indício" — e **nunca** "hora extra".
- **Marca:** a interface carrega a marca do tenant, nunca a do fornecedor. Cor de marca é token CSS (`frontend/src/app/globals.css`) e nome é configuração (`frontend/src/lib/brand.ts`) — nunca literal em componente. O laranja `#FF8C00` é preenchimento com texto escuro por cima, jamais texto e jamais sob texto branco; laranja de texto é `#A85F00`.
- **Vocabulário de produto:** é sempre *desvio* ou *indício*. **Nunca "hora extra"** — o registro oficial é o Secullum, e divergência com ação do gestor em cima é exposição do fornecedor.
- **Commits:** Conventional Commits. A mensagem explica **por quê**, não o quê.
- **Branches:** `feature/*`, `fix/*` a partir de `main`; PR com review.

### Regras de segurança que não se quebram

Se uma tarefa parecer exigir violar alguma destas, **pare e pergunte**. É sinal de
que o desenho está errado, não a regra.

**Regra 0 — autorização de produção é condicionada às premissas escritas nela.**
Toda autorização do dono para mexer em produção vale enquanto as premissas
declaradas nela continuarem verdadeiras. Premissa derrubada pela própria
investigação = **autorização revogada na hora**: voltar e perguntar, com o que
mudou na mão. A revogação é automática e reconhecê-la é obrigação de quem
executa — não é preciso que o dono a anuncie. Nasceu de
`docs/INCIDENTE-2026-08-27-EXPOSED-SCHEMAS.md`, em que uma autorização válida foi
executada minutos depois de a investigação derrubar a premissa dela, e derrubou
a sincronização de produção.
**Em 27/08/2026 todas as autorizações anteriores foram revogadas**, por terem
sido dadas sob a arquitetura "a sync roda em Edge Functions".

1. Nenhuma tabela em `public`. Tabela vai para `app` ou `secullum`.
2. Toda view de `public` com `security_invoker = on`.
3. Toda tabela de `app` com `tenant_id` e RLS.
4. `service_role` só no backend FastAPI, e nenhuma consulta sem filtro de `tenant_id`.
5. Agregação por empresa vai por `colaborador → empresa`, nunca `departamento → empresa` (~26% divergem na FastPark).
6. Nunca deletar desvio — usar `app.revoke_deviation()`.
7. Alerta de conteúdo individual nunca vai para grupo.
8. Nenhum alerta enviado antes do modo sombra fechar com falso positivo ≤5%.
9. Nada de text-to-SQL no assistente.
10. Dado de saúde guarda só aptidão e validade — nunca diagnóstico, CID ou restrição.
11. Provedor de WhatsApp recebe `(template, variáveis, destino)` — **nunca string pronta**. Os três (`meta_cloud`, `z_api`, `uazapi`) ficam atrás desse contrato; texto livre exclui o oficial de forma irreversível.
