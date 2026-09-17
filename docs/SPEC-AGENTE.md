<!-- verificar-docs: inexistentes-de-proposito app.assistant_metric_scope app.assistant_metric_scope.enabled app.ai_query.prompt_version_id app.ai_query.is_dry_run public.fn_assistant_catalog app.work_schedule_day -->
<!-- `app.work_schedule_day` entra na lista porque este documento a CITA para
     contar o erro que ela causou na etapa DP. Ela nunca existiu — ver
     `SPEC-DP.md` §0-bis, que registra as três camadas que existem de verdade. -->

# OperaX — SPEC da tela de configuração do assistente

Traz para o OperaX o padrão de administração de agente que o **DeskcommCRM** já
tem em produção: configuração versionada, publicação atômica, teste antes de
subir, histórico com rollback, e leitura do que o agente realmente usou.

O DeskcommCRM foi lido inteiro (34 arquivos de tela, 13 rotas de API, 5
migrations). O que segue **não é um port**. Metade do padrão de lá resolve um
problema que o OperaX não tem, e uma parte dela, copiada, demoliria uma regra
deste produto. A §6 lista item a item o que fica de fora e por quê — é a seção
mais importante deste documento.

---

## ⚠️ Procedência das afirmações — leia antes de confiar na §0

Vale aqui a mesma advertência da `SPEC-DP.md`. As verificações que originaram
este documento rodaram contra o **snapshot de 15 migrations** deste diretório,
não contra o repositório em andamento (37) nem contra produção.

Toda linha da §0 que diz "já existe" precisa ser reconferida no repo em
andamento antes de virar premissa de código. O erro do `app.work_schedule_day`
na etapa DP foi exatamente este, e custou um sprint de replanejamento.

Especificamente a reconferir:

- `app.metric` ainda tem `code` como PK e **nenhum** `tenant_id`?
- a policy `metric_read` continua `using (active)`, sem filtro de tenant?
- `app.ai_query` continua com as 13 colunas da §0.3, sem vínculo a config?
- `backend/operax/agente/catalogo.py` existe e é quem monta o catálogo?

---

## §0. O que o OperaX tem hoje

### 0.1 O assistente existe; a administração dele não

`CLAUDE.md` e `SPEC-TECNICA.md` §7 descrevem um agente LangChain 1.x
(`create_agent`) em `backend/operax/agente/`, servido por
`POST /assistente/perguntar` com SSE. Ele funciona.

O que não existe é **qualquer superfície para configurá-lo**. O prompt de
sistema, o provedor, o modelo e a allowlist vivem em código e variáveis de
ambiente. Consequências práticas, todas verdadeiras hoje:

- mudar uma palavra do prompt é deploy;
- não há registro de qual texto de prompt produziu qual resposta;
- não há como voltar atrás sem `git revert`;
- o cliente não tem como ver, nem influenciar, o que governa o assistente dele.

### 0.2 `app.metric` — o catálogo fechado

```sql
create table if not exists app.metric (
  code        text primary key,
  title       text not null,
  description text not null,
  target_view text not null,           -- view em `public`, jamais tabela
  dimensions  text[] not null default '{}',
  filters     text[] not null default '{}',
  domain      app.sensitive_domain,    -- null = não sensível
  active      boolean not null default true
);
```

Oito métricas semeadas. Duas com domínio: `documents_expiring` (`pii`) e
`payroll_summary` (`compensation`).

**Dois fatos com consequência de projeto:**

1. **Não há `tenant_id`.** O catálogo é da plataforma, não do cliente. Isso está
   certo e deve continuar: uma métrica exige que a view/RPC alvo exista, o que
   exige migration. `CLAUDE.md` já obriga *"inserir em `app.metric` **e**
   garantir que a view/RPC alvo existe — sempre no mesmo PR"*.
2. **A policy é `using (active)`** — todo usuário autenticado lê o catálogo
   inteiro. É um cardápio, não dado: títulos de métrica são vocabulário de
   produto. Mas significa que **não existe hoje nenhum lugar onde registrar que
   um cliente não usa uma métrica**. É a lacuna que a aba "Capacidades" precisa.

### 0.3 `app.ai_query` — o log de execuções, sem âncora

Já registra `question`, `metric_code`, `parameters`, `rows_returned`,
`latency_ms`, `input_tokens`, `output_tokens`, `refused`, `refusal_reason`.

O `refused` merece nota: o log já modela **recusa como resposta válida**, que é
a doutrina da SPEC-TECNICA §7. Isso é raro e é bom.

O que falta é o vínculo: **nenhuma linha diz qual configuração a produziu.** O
comentário na própria coluna `output_tokens` diz por que isso dói:

> *"Custo de LLM é variável e sai da sustentação mensal. Sem medir, não dá para
> saber se a margem virou negativa."*

Token não vira custo sem preço, e preço depende do modelo. Se o modelo pode
mudar entre versões de configuração — e o objetivo desta etapa é justamente que
possa —, então **a FK para a versão é o que faz as colunas de token
responderem à pergunta para a qual foram escritas.** Não é feature nova; é
conserto de uma existente.

### 0.4 A guarda de arquitetura é física, não convencional

`util.block_table_in_public()`, event trigger em `CREATE TABLE`, **rejeita** a
criação de tabela em `public`. O DeskcommCRM põe todas as suas tabelas em
`public`. Cópia literal de qualquer DDL de lá **falha na hora**, com a mensagem
certa. Isso é uma boa notícia: o erro é impossível de cometer em silêncio.

---

## §1. A decisão de projeto que não é óbvia: de quem é o prompt

O DeskcommCRM dá a cada organização a configuração inteira — prompt, provedor,
modelo, credencial, orçamento. Faz sentido lá: cada cliente traz a própria chave
de API e paga o próprio consumo.

No OperaX **isso está errado em um ponto específico**, e o ponto importa: o
prompt de sistema carrega a **doutrina** do produto — sem text-to-SQL, sempre
declarar período e filtros, recusar é resposta válida. Se um cliente pode
reescrever o prompt inteiro, um cliente pode apagar a doutrina. Não por
maldade: por um "seja mais direto, não fique explicando" bem-intencionado que
remove a linha que manda mostrar o filtro usado.

### A forma: duas camadas, uma soma

O próprio DeskcommCRM tem o padrão certo, em outra tabela — `playbook_versions`,
com `layer in ('platform','tenant','campaign')` e o check que amarra escopo a
dono. Adoto a forma, com duas camadas:

| Camada | Dono | Conteúdo | Editável pelo painel |
|---|---|---|---|
| `platform` | EURECA | doutrina, contrato de recusa, formato da resposta | **não** — migration |
| `tenant` | `owner` do cliente | vocabulário local, contexto de operação, tom | sim |

O prompt efetivo é `platform` **seguido de** `tenant`. A camada do cliente é
**acrescentada, nunca substituída**. Limite de tamanho validado na escrita — o
DeskcommCRM usa 200 linhas por camada e a razão é a mesma aqui: camada sem
limite vira lugar onde alguém cola um manual inteiro e ninguém percebe o custo
por turno.

### Quem edita a camada `platform`

**Ninguém, pelo painel.** `app.user_role` tem nove papéis e todos são papéis
*dentro de um tenant*: não existe papel de plataforma. Criar um seria criar uma
classe nova de objeto de segurança — um papel que atravessa tenants — para
editar um campo de texto. Não compensa.

A camada `platform` é semeada por migration. O painel a exibe **em modo de
leitura**, para o cliente ver o que governa o assistente dele. Transparência sem
papel novo.

⛔ **Não-objetivo explícito:** papel de plataforma. Se aparecer na
implementação, é escopo que entrou sem decisão.

---

## §2. Versões imutáveis + ponteiro (e não flags de status)

O DeskcommCRM tem **os dois** padrões, no mesmo repositório, e a comparação
entre eles é a evidência de qual escolher:

| | `ai_agent_versions` (flags) | `playbook_versions` (ponteiro) |
|---|---|---|
| publicar | RPC de 159 linhas, 14 recusas nomeadas | um `update` no ponteiro |
| imutabilidade | trigger que **enumera 17 colunas** de conteúdo e isenta 3 de ciclo de vida | trigger de uma linha: todo `update` levanta exceção |
| coluna nova | precisa ser adicionada ao trigger, ou fica mutável **em silêncio** | nada a fazer |
| rollback | republicar (novo `published_at`, `superseded_at` do outro) | mover o ponteiro |

O trigger de enumeração (`0051_agent_version_immutability.sql`) é uma armadilha
de manutenção conhecida: quem adicionar uma coluna a `ai_agent_versions` e não
mexer no trigger cria um campo mutável depois de publicado, sem erro nenhum.

**Escolha: ponteiro.** E ela mata um bug de produção antes de existir — o que
`lib/ai/agents/versoes-da-tela.ts` documenta em 45 linhas de comentário:

> *"Abri o agente e o prompt sumiu." A tela mostrava 21 tokens enquanto a versão
> publicada, com 16.714 caracteres, atendia normalmente. E o botão oferecia
> "Publicar v6": um clique e o texto vazio substituiria o bom.*

A causa foi `draft ?? published` — rascunho vencendo sempre, inclusive quando
mais **antigo** que a publicada. A causa raiz é anterior: rascunho e versão
publicada moram na **mesma tabela**, distinguidos por uma coluna de status, e
por isso "qual das duas a tela abre" é uma pergunta que precisa de resposta.

### O desenho: três tabelas com papéis que não se confundem

```
app.assistant_draft            1 linha por escopo · MUTÁVEL   · o editor abre esta
app.assistant_prompt_version   append-only        · IMUTÁVEL  · o histórico
app.assistant_prompt_pointer   1 linha por escopo · MUTÁVEL   · o runtime lê esta
```

- **O editor sempre abre o rascunho.** Sem rascunho, ele é criado a partir da
  versão apontada. Nunca há disputa.
- **O runtime sempre lê pelo ponteiro.** Nunca vê rascunho.
- **Publicar** = congelar o rascunho em versão + mover o ponteiro, atômico.

### O caso que ainda existe, e a tela precisa dizer

Rollback move o ponteiro para uma versão antiga enquanto o rascunho continua com
o texto novo. Então o rascunho fica **mais recente** que o que está no ar.

Isso não é defeito, é o estado real — e é exatamente o estado que o DeskcommCRM
escondia. `app.assistant_draft.frozen_from_version_id` torna a comparação
**computável em vez de adivinhada**: se ele aponta para uma versão que não é a
apontada pelo ponteiro, a tela diz, com as duas visíveis:

> *"Seu rascunho partiu da v7. No ar está a v3. Publicar substitui a v3."*

⛔ **Requisito de tela, não de banco:** nunca esconder um dos dois. O modo de
falhar aqui é o clique que substitui o texto bom pelo que a tela não mostrava.

---

## §3. Migrations

Cinco, na ordem. Nomes no padrão da etapa DP.

### §3a — `assistant_prompt_layers`

```sql
create table if not exists app.assistant_prompt_version (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid references app.tenant(id) on delete cascade,  -- NULL = plataforma
  layer         text not null check (layer in ('platform','tenant')),
  version_number integer not null,
  content       text not null,
  -- Só a camada de plataforma decide modelo: quem escolhe o modelo gasta o
  -- dinheiro da EURECA (ver §6.2). Nas duas colunas, NULL na camada do tenant.
  provider      text check (provider in ('openai','anthropic','google')),
  model         text,
  max_steps     smallint check (max_steps between 1 and 10),
  created_at    timestamptz not null default now(),
  created_by    uuid references auth.users(id),
  constraint assistant_prompt_scope_coerente
    check ((layer = 'platform') = (tenant_id is null)),
  constraint assistant_prompt_modelo_so_na_plataforma
    check ((layer = 'platform') or (provider is null and model is null and max_steps is null)),
  constraint assistant_prompt_tamanho
    check (length(content) <= 12000)
);

create unique index if not exists assistant_prompt_version_tenant_uk
  on app.assistant_prompt_version (tenant_id, layer, version_number)
  where tenant_id is not null;
create unique index if not exists assistant_prompt_version_platform_uk
  on app.assistant_prompt_version (layer, version_number)
  where tenant_id is null;
```

O par de índices parciais existe porque `tenant_id` é `NULL` na plataforma e
`unique` não serve para `NULL` — é o mesmo motivo pelo qual o DeskcommCRM tem
`uniq_playbook_pointers_org` e `uniq_playbook_pointers_platform` separados.

**Imutabilidade — uma linha, sem enumerar coluna:**

```sql
create or replace function util.assistant_version_immutable() returns trigger
language plpgsql as $$
begin
  raise exception 'app.assistant_prompt_version é imutável: mudança = versão nova; rollback = mover o ponteiro (app.assistant_prompt_pointer)';
end $$;

create trigger trg_assistant_version_immutable
  before update on app.assistant_prompt_version
  for each row execute function util.assistant_version_immutable();
```

`delete` fica de fora de propósito: o cascade de `app.tenant` precisa passar, e
a versão apontada é protegida pela FK do ponteiro.

**Ponteiro:**

```sql
create table if not exists app.assistant_prompt_pointer (
  tenant_id  uuid references app.tenant(id) on delete cascade,   -- NULL = plataforma
  layer      text not null check (layer in ('platform','tenant')),
  version_id uuid not null references app.assistant_prompt_version(id),  -- SEM cascade
  updated_at timestamptz not null default now(),
  updated_by uuid references auth.users(id),
  constraint assistant_pointer_scope_coerente
    check ((layer = 'platform') = (tenant_id is null))
);

create unique index if not exists assistant_pointer_tenant_uk
  on app.assistant_prompt_pointer (tenant_id, layer) where tenant_id is not null;
create unique index if not exists assistant_pointer_platform_uk
  on app.assistant_prompt_pointer (layer) where tenant_id is null;
```

**Sem `on delete cascade` no `version_id`, de propósito:** versão apontada não
pode sumir debaixo do ponteiro.

**Sem `primary key`, e os dois índices parciais no lugar dela:** `tenant_id` é
`NULL` na plataforma e PK não aceita `NULL`. Sem eles a tabela aceita dois
ponteiros para o mesmo escopo, e aí *"qual versão está no ar"* deixa de ter
resposta — que é a única pergunta que esta tabela existe para responder.

**Rascunho:**

```sql
create table if not exists app.assistant_draft (
  tenant_id  uuid not null references app.tenant(id) on delete cascade,
  content    text not null,
  frozen_from_version_id uuid references app.assistant_prompt_version(id),
  updated_at timestamptz not null default now(),
  updated_by uuid references auth.users(id),
  primary key (tenant_id),
  constraint assistant_draft_tamanho check (length(content) <= 12000)
);
```

Só camada de tenant tem rascunho — a de plataforma vem por migration.

⛔ **Parada obrigatória:** três tabelas novas em `app` com policy de RLS.
Escrito aqui **não é autorizado** aqui.

### O DDL da §3a foi executado, não só escrito

Rodado em PostgreSQL 16.13 contra um schema mínimo (`app.tenant`, `auth.users`,
o enum). Sete comportamentos verificados — os quatro últimos são os que uma
revisão de código não pega:

| # | Cenário | Resultado |
|---|---|---|
| 1 | camada `platform` **com** `tenant_id` | rejeitado — `assistant_prompt_scope_coerente` |
| 2 | camada `tenant` escolhendo `model` | rejeitado — `assistant_prompt_modelo_so_na_plataforma` |
| 3 | um `platform` + um `tenant` válidos | aceitos |
| 4 | `update` numa versão | rejeitado pelo trigger, com a mensagem que ensina o caminho |
| 5 | **segundo ponteiro de plataforma** (`tenant_id` NULL nos dois) | rejeitado — o índice parcial pega o caso `NULL`, que uma PK não pegaria |
| 6 | `delete` da versão **apontada** | rejeitado — FK sem cascade protege |
| 7 | `delete` do tenant inteiro | **passa**, e leva versões e ponteiro junto |

O par 6/7 é o ponto delicado e o motivo de ter sido testado: a versão precisa
ser indestrutível enquanto apontada **e** o cascade de `app.tenant` precisa
continuar passando. São requisitos que se contradizem no papel. Passam porque o
ponteiro morre primeiro no cascade, e aí a FK não tem mais o que proteger — e
porque o trigger é `before update`, não `before delete`. Nenhuma das duas coisas
é óbvia lendo o DDL; por isso a linha 7 existe.

Script em `/tmp/claude-0/behavior.sql` (efêmero). **Transcrever como
`tests/db/test_assistant_immutability.sql` é parte do S1**, não item opcional:
verificação que não vira teste é verificação que expira.

**RLS** — leitura da camada de plataforma é aberta a `authenticated` (é o que
torna a transparência da §1 possível); tudo de tenant exige `util.is_admin`:

```sql
-- versão: plataforma legível por todos; tenant só pelo próprio tenant
create policy assistant_version_read on app.assistant_prompt_version
  for select to authenticated
  using (tenant_id is null or util.has_tenant(tenant_id));
-- escrita: nenhuma policy para authenticated. Só o RPC (§3d) e service_role.
```

### §3b — `assistant_metric_scope`

```sql
create table if not exists app.assistant_metric_scope (
  tenant_id   uuid not null references app.tenant(id) on delete cascade,
  metric_code text not null references app.metric(code) on delete cascade,
  enabled     boolean not null,
  updated_at  timestamptz not null default now(),
  updated_by  uuid references auth.users(id),
  primary key (tenant_id, metric_code)
);
```

**Ausência = habilitada.** A tabela guarda só as exceções. O motivo não é
economia de linha: se ausência significasse desabilitada, uma métrica nova
semeada pela EURECA nasceria invisível para todos os clientes existentes, e o
sintoma seria *"o assistente parou de responder sobre X"* sem nada nos logs. A
falha silenciosa é o critério, não o tamanho da tabela.

### §3c — `assistant_run_link`

```sql
alter table app.ai_query
  add column if not exists prompt_version_id uuid references app.assistant_prompt_version(id),
  add column if not exists is_dry_run boolean not null default false;

create index if not exists ai_query_dry_run_idx
  on app.ai_query (tenant_id, created_at desc) where not is_dry_run;
```

`prompt_version_id` é **nullable**: as linhas que já existem não têm versão, e
inventar uma para elas seria mentira gravada. A tela lê "antes do versionamento"
quando é nulo.

O índice parcial exclui dry-run porque a tela de execuções e a conta de margem
falam de tráfego real; teste na média de custo por consulta é ruído.

### §3d — `assistant_publish_fn`

Publicação atômica: congelar o rascunho em versão nova **e** mover o ponteiro.
Dois `update`/`insert` em statements separados deixam o banco inconsistente numa
falha parcial — é o mesmo argumento que o DeskcommCRM escreve no cabeçalho de
`0024_ai_agent_publish_fn.sql`, e vale igual aqui.

```sql
create or replace function public.fn_publish_assistant_prompt(p_tenant_id uuid)
returns table (version_id uuid, version_number integer, previous_version_id uuid)
language plpgsql
security definer
set search_path = ''
as $$ ... $$;
```

Validações, na ordem, cada uma com código de erro próprio (`P0001`, mensagem =
código, como no DeskcommCRM):

1. `not_admin` — `util.is_admin(p_tenant_id)` falso. **A função é `security
   definer`: ela precisa checar o papel ela mesma**, porque não herda a RLS de
   quem chamou. Vem **antes** de tudo, inclusive de saber se há rascunho: o
   owner de outro tenant não aprende se este tem rascunho (nem se existe) —
   medido em 17/09/2026, com a ordem invertida os dois códigos vazavam o bit;
2. `draft_not_found` — não há rascunho para o tenant;
3. `draft_empty` — conteúdo em branco;
4. `platform_layer_missing` — não há ponteiro de plataforma. Publicar camada de
   tenant sem doutrina embaixo produziria um assistente sem contrato de recusa;
5. `draft_unchanged` — idêntico à versão apontada. Versão nova sem diferença
   polui o histórico e faz o rollback mentir.

**Trava contra publicação concorrente.** `version_number` é calculado por
`max(...)+1`; duas publicações simultâneas do mesmo tenant leem o mesmo máximo e
a segunda morre no índice único — erro de banco cru numa tela. A primeira
instrução da função trava a linha do rascunho, que é o único objeto que sempre
existe no momento de publicar (o ponteiro não existe na primeira publicação):

```sql
select content, frozen_from_version_id into v_draft
from app.assistant_draft where tenant_id = p_tenant_id
for update;                                  -- serializa daqui em diante
v_found := found;                            -- julgado só depois do papel
```

⚠️ **`set search_path = ''`** e todo objeto qualificado, como todas as funções
`util` deste repo. E atenção: `trg_lock_down_new_function` **não dispara para
funções em `public`** (só `util` e `app`) — o `grant execute` para
`authenticated` precisa ser **escrito explicitamente** na migration. Não há rede
de segurança aqui, nos dois sentidos.

### §3e — `assistant_catalog_fn`

```sql
create or replace function public.fn_assistant_catalog(p_tenant_id uuid)
returns table (code text, title text, description text, domain app.sensitive_domain,
               enabled boolean, visible_to_me boolean)
```

O catálogo efetivo do tenant, com os três filtros da §4 resolvidos numa
resposta só. É o que a aba "Capacidades" lê **e** o que `catalogo.py` chama —
ver §4.3, que é onde está o motivo de ser uma função só.

---

## §4. Capacidades = métricas

### 4.1 A invariante que define o risco da tela inteira

> **Habilitar uma métrica não concede acesso a dado.** O executor roda a view
> **como o usuário**; a RLS dele decide o que volta. A lista de capacidades só
> **estreita**: desabilitar tira a métrica do catálogo que o modelo enxerga.
> Habilitar nunca amplia além do que o papel já podia.

Consequência direta e útil: um defeito nesta tela é um defeito de
**disponibilidade** — alguém não consegue perguntar algo —, nunca de vazamento.
Isso decide quanto escrutínio a tela merece, e a resposta é: menos que uma tela
de permissão. Ela **não é** uma tela de permissão, e não deve ser desenhada nem
nomeada como se fosse.

⛔ Se em algum momento habilitar uma métrica passar a conceder algo, esta
invariante caiu e a tela vira outra coisa. É condição de parada.

### 4.2 Três filtros, todos estreitando

```
app.metric.active                    (EURECA: a métrica existe no produto)
        ↓
app.assistant_metric_scope.enabled   (cliente: nós usamos isso)
        ↓
util.can_see_domain(tenant, domain)  (papel: esta pessoa pode ver)
```

Nunca ao contrário, em nenhum dos três.

### 4.3 Uma régua só — a lição que o DeskcommCRM pagou para aprender

Em `versoes-da-tela.ts`, tela e escrita tinham réguas próprias e discordavam
exatamente no caso raro; o resultado foi trabalho sobrescrito em silêncio. Eles
consolidaram numa função e escreveram um teste que **cobra que todo chamador de
produção use o ponteiro**.

Mesma disciplina, mesmo motivo: `public.fn_assistant_catalog` é a régua única.
Se a aba "Capacidades" reimplementar o filtro em TypeScript, ela e o runtime vão
divergir — e a divergência aparece como *"a tela diz que está ligada e o
assistente diz que não tem esse dado"*, que é indistinguível de bug do modelo e
custa dias para diagnosticar.

**Teste do gate:** um teste que falha se `catalogo.py` montar o catálogo por
query própria em vez de chamar a RPC.

### 4.4 O que a tela não tem

**Não há botão "criar métrica".** Métrica exige view/RPC, que exige migration —
`CLAUDE.md` já obriga o par no mesmo PR. Pedir métrica nova é chamado, não
formulário. O botão, se existisse, precisaria ou aceitar nome de view digitado
pelo cliente (que é text-to-SQL com outro nome) ou não fazer nada.

---

## §5. Teste: onde o OperaX é mais perigoso que o DeskcommCRM

O painel de teste de lá é seguro por construção: `is_dry_run=true`, e a rota
*"nunca toca contacts/conversations, nunca chama WAHA, nunca cria
messages.outbound"*. Nada sai; nada é lido de sensível.

**No OperaX o teste lê dado real.** O executor roda como o usuário, então
"testar" é executar uma consulta de verdade sobre colaboradores de verdade. Não
há sandbox, e não deveria haver: um assistente testado contra dado falso é
testado contra outro produto.

Isso é aceitável — a mesma pessoa poderia ter feito a mesma pergunta no chat, e
veria o mesmo. Mas duas coisas mudam:

1. **A tela diz.** *"O teste consulta dados reais, com as suas permissões."*
   Uma linha. A ausência dela é o que faz alguém colar dado de produção num
   canal errado achando que era exemplo.
2. ⛔ **O teste nunca roda como outro papel.** "Como isso ficaria para um
   supervisor?" é uma pergunta legítima com uma resposta legítima — *listar
   quais métricas aquele papel alcança* — e uma resposta ilegítima: executar
   como ele. A segunda é escalação de privilégio com nome de recurso, e a única
   defesa é não construir o caminho.

Registro: `app.ai_query` com `is_dry_run = true` e `prompt_version_id` da versão
testada. Rascunho é testável — é o principal motivo de testar — e nesse caso
`prompt_version_id` fica nulo com o `question` prefixado; alternativa em §7.

---

## §6. O que **não** vem do DeskcommCRM

### 6.1 Todo o aparato de agente autônomo — e por que é perigoso

Ficam de fora: `channel_session_id`, `trigger_config` (events / filters /
concurrency), `handoff_keywords`, `handoff_tool_enabled`, e o índice único
parcial `ai_agent_runs_one_running_per_conv`.

Motivo direto: **o assistente do OperaX é pull.** Alguém pergunta, ele responde
por SSE. Ele nunca inicia, nunca responde sozinho, não tem conversa que possa
receber duas respostas. Gatilho, concorrência e handoff resolvem problemas que
este produto não tem.

Motivo indireto — **corrigido em 05/09/2026**, ver a nota abaixo:

> O OperaX **tem** caminho de saída para WhatsApp — `app.alert_queue`, outbox +
> sender —, **exclusivamente por template**, sob a regra 11. Trazer
> `trigger_config` e `channel_session_id` para a configuração do assistente
> constrói, dentro de uma tela de administração, o mecanismo pelo qual um agente
> compõe e envia texto livre. Duas coisas quebram, e nenhuma é a que este
> documento afirmava na primeira versão:
>
> 1. **A regra 11 cai, e o custo dela é comercial.** O que a regra protege é a
>    viabilidade do provedor **oficial**: *"texto livre exclui o oficial de forma
>    irreversível"*. Sem `meta_cloud`, sobram `z_api` e `uazapi`, e
>    `DECISAO-WHATSAPP.md` §1 é explícito sobre o que isso significa — banimento
>    **do número, permanente, sem recurso**, e *"se o número banido for o da
>    Kastro Park, quem explica é a EURECA"*.
> 2. **O modelo de segurança do assistente para de valer.** Ele é seguro porque
>    o executor roda **como o usuário** e a RLS dele decide o que volta. Uma
>    mensagem no telefone não tem sessão, não tem papel e não tem RLS. Mandar
>    saída do assistente para um canal move o dado para fora do único mecanismo
>    que o tornava seguro. Este argumento é **independente da regra 11** e
>    sobrevive mesmo se a regra 11 mudar.

⚠️ **Correção de 05/09/2026 — eu errei a razão da regra 11 e o erro era meu.**
A primeira versão desta seção afirmava que a regra 11 *"existe para que nenhum
texto livre chegue ao WhatsApp de uma pessoa"*. **Não é isso.** O `CLAUDE.md`
diz: *"Provedor de WhatsApp recebe `(template, variáveis, destino)` — nunca
string pronta. Os três ficam atrás desse contrato; texto livre exclui o oficial
de forma irreversível."* A regra é de **interoperabilidade**, não de privacidade:
uma vez montada a string, a informação estruturada que o template da Meta exige
já se perdeu. As regras de privacidade são a 7 (conteúdo individual nunca vai
para grupo) e a 10 (saúde sem diagnóstico).

Atribuí a uma regra um propósito que ela não declara, sem ler o texto dela —
que é a mesma classe de erro do `app.work_schedule_day`. A conclusão sobrevive,
com argumento melhor; a afirmação original, não.

⛔ Se aparecer `channel_session_id` na configuração do assistente, pare: virou
outro produto, e a decisão não foi tomada. **Isto vale para a configuração do
assistente, não para o produto.** Uma tela de administração dos canais que o
OperaX já tem é outra coisa, é legítima, e está especificada em
`SPEC-CANAIS.md`. A linha que não se cruza é **assistente → sender**, não
"OperaX não administra canal".

### 6.2 Credencial por tenant (`ai_provider_credentials`)

Lá, cada organização traz a própria chave. No OperaX o modelo é pago pela
EURECA e sai da sustentação mensal — é o que diz o comentário em
`app.ai_query.output_tokens`. Credencial fica em variável de ambiente, no
backend, uma por plataforma.

Corolário já embutido na §3a: `provider` e `model` só existem na camada
`platform`. Cliente escolhendo modelo é cliente gastando dinheiro da EURECA.

### 6.3 Orçamento por tenant

`token_budget` e `cost_budget_cents` por agente resolvem o problema de quem
paga por org. Aqui já existe **rate limiting por usuário** em
`POST /assistente/perguntar` (`CLAUDE.md`), que é a defesa contra abuso de
custo. `max_steps` vem — mas na camada de plataforma, e como teto de segurança,
não como orçamento.

### 6.4 O flywheel de propostas

`flywheel_judge_verdicts`, `flywheel_distiller_proposals`,
`judge_alignment_pool`, a aba "Propostas" e a migration `0053`: **fora de
escopo agora**, e não por tamanho.

A precondição não é técnica, é de dados: propor melhoria de prompt exige um
conjunto de execuções **julgadas** — esta recusa estava certa, aquela estava
errada. O OperaX tem a matéria-prima (`app.ai_query.refused` +
`refusal_reason`) e não tem o julgamento. Sem ele, o distiller propõe mudança a
partir de ruído, com a autoridade de uma tela.

**O destrave é nomeado:** quando existir rotulagem de recusa — mesmo manual,
mesmo por uma pessoa, mesmo 200 linhas — a aba passa a fazer sentido. Antes
disso, não. Um botão "Propostas" vazio numa tela é pior que ausente: ele promete.

### 6.5 `public` como schema de tabela

Óbvio, mas registrado porque é o erro mais provável ao ler o código de lá: toda
tabela criada em `public` no DeskcommCRM nasce em `app` aqui, com `tenant_id` e RLS.
`trg_block_table_in_public` rejeita a alternativa na hora — a guarda é física.
E `organization_id` → `tenant_id` em toda linha copiada.

---

## §7. Perguntas em aberto — do owner, não da implementação

1. **Rascunho testado gera versão?** A §5 deixa `prompt_version_id` nulo no
   teste de rascunho, o que torna *"qual texto produziu este teste"*
   irrecuperável. Alternativa: congelar em versão a cada teste — histórico
   fiel, mas o histórico enche de versões que nunca foram publicadas.
   Terceira via: coluna `draft_content_hash` em `app.ai_query`, que identifica
   sem versionar. Sugiro a terceira; é decisão sua.

2. **Quantas versões guardar?** Append-only sem poda cresce sem teto. Não é
   urgente (texto, um por publicação) e uma decisão precipitada aqui vira
   `delete` de histórico, que a §2 diz que não deve existir. Sugiro **não podar
   nesta etapa** e revisitar com número real na mão.

3. **O cliente edita a camada dele desde o dia 1?** A §1 dá ao `owner` do
   tenant o direito de escrever. Se a preferência for começar com a tela
   somente-leitura para os dois níveis — cliente vê, EURECA edita por migration
   — o modelo de dados não muda em nada; muda só quem recebe o `grant`. É
   reversível nos dois sentidos e não bloqueia sprint nenhum.

---

## §8. Fora de escopo, nomeado

Agente autônomo em WhatsApp (§6.1), credencial por tenant (§6.2), orçamento por
tenant (§6.3), flywheel de propostas (§6.4, com destrave nomeado), papel de
plataforma (§1), botão de criar métrica (§4.4), e teste executando como outro
papel (§5) — este último não é "fora de escopo", é **proibido**.
