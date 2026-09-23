<!-- verificar-docs: inexistentes-de-proposito app.messaging_identity app.messaging_invite app.channel_health public.fn_channel_readiness public.fn_telegram_adhesion -->

# OperaX — sprints de canais

Implementação de `SPEC-CANAIS.md`. Cinco sprints. Gate que não fecha = sprint
que não terminou.

**C1 e C2 entregam valor sozinhos** — a tela de Conexões conserta o diagnóstico
invisível de hoje, sem Telegram nenhum. Se a etapa parar no C2, ela ainda valeu.

---

## C0 — Reconferência

Escrita contra **15 migrations**; o repo tem **37**. Cinco perguntas:

1. `integration_whatsapp_unico_ativo` ainda tem o predicado com os três
   provedores nominais?
2. `app.integration_secret` ainda guarda **só** `vault_id`, sem policy para
   `authenticated`?
3. `fn_whatsapp_readiness` ainda devolve as sete colunas da SPEC §0?
4. `app.contact` ainda é o único modelo de destinatário, sem colaborador?
5. `app.message_template.body` ainda é o caminho de render local?

Um "não" na 2 muda a §5 inteira; na 5, muda a §2.

### ✅ Respondido em 05/09/2026 — cinco de cinco, nenhum "não"

Medido contra o repositório em andamento (37 migrations), lendo as migrations e
o código, não a documentação.

| # | Resposta | Onde |
|---|---|---|
| 1 | ✅ **sim** — `on app.integration (tenant_id) where active and provider in ('meta_cloud','z_api','uazapi')`. Os três nominais | `14_whatsapp_provedores.sql` |
| 2 | ✅ **sim** — a tabela é `integration_id · key · vault_id · updated_at`, só o ponteiro. **Sem policy**, com `revoke all … from authenticated` e `grant all … to service_role` explícitos | `09_integracoes_auditoria.sql` |
| 3 | ✅ **sim** — as sete: `tenant_id · provider · official · templates_total · templates_approved · rules_blocked · ready`. `security definer`, recortada por `util.user_tenants()`, com `execute` para `authenticated` | `14_whatsapp_provedores.sql` |
| 4 | ✅ **sim** — `app.contact` é `name · whatsapp · email · type`, e `type` só aceita `person`, `whatsapp_group`, `email_list`. **Nenhum elo com `app.employee`** | `04_organizacao_colaborador.sql` |
| 5 | ✅ **sim** — `body text not null` comentado como *"render local (z_api/uazapi) com {{1}}, {{2}}"*, com `trg_validate_template_body` conferindo os placeholders | `14_whatsapp_provedores.sql` |

📌 **A 1 confirma o item 4 do briefing pelo lado do dado:** o predicado é
nominal, então acrescentar `'telegram'` ali tornaria os dois canais mutuamente
exclusivos. O índice irmão é a saída, e não é preferência de estilo.

📌 **A 3 confirma o defeito que C1 conserta:** a função está pronta, recortada
por tenant e já concedida a `authenticated` — o Caminho 1 alcança. Falta só a
tela. C1 é leitura, não cálculo novo.

📌 **A 4 foi registrada em `SPRINTS-DP.md`, S4**, como o briefing pediu — os dois
templates de lá são endereçados ao colaborador e não têm destinatário.

---

## C1 — Tela de Conexões, sem Telegram

**Por que primeiro:** é o único sprint que entrega valor sem nada novo no banco.
Tudo que ele mostra já existe e já está calculado.

- Módulo de capabilities (SPEC §1) com os **três** provedores atuais.
  Fail-closed: provedor desconhecido lança. Default = o conservador.
- Tela: provedor ativo, saúde, `templates_approved`, `rules_blocked`, e a frase
  que explica o bloqueio.
- Aba de templates com sincronização de `meta_status` a partir da WABA.
- ⛔ Campos com `autocomplete` correto e validação de formato (SPEC §5.4) — o
  defeito visível nas capturas do DeskcommCRM não é para ser copiado.

**Gate:** um tenant com regra ligada apontando para template `pending` mostra na
tela **qual** template e **qual** regra. Hoje esse estado existe, é calculado por
`fn_whatsapp_readiness` e é invisível — é o defeito que este sprint fecha, e o
teste é ver a frase na tela, não a função devolver `false`.

### ✅ C1, metade de backend — aprovada em 13/09/2026, dois ciclos

**Ciclo 1: REPROVADO** (2 ALTO, 3 MÉDIO, 3 BAIXO). **Ciclo 2: APROVADO.** Portões
medidos por mim: `pytest` **675** (baseline 639), `ruff` limpo, suíte de banco
`SUÍTE COMPLETA OK` com um bloco novo (`scripts/97_teste_canais.py`).

**Antes de despachar, o C0 foi refeito.** As cinco respostas de 05/09 tinham sido
medidas contra 37 migrations; o repo tinha 53. Reconferidas uma a uma contra o
schema: cinco "sim", nenhum "não".

**O que entrou:**
- `backend/operax/alertas/capacidades.py` — a doutrina da SPEC §1: um registro
  congelado por provedor, as duas famílias de restrição como dados, fail-closed
  (desconhecido lança), default conservador com o motivo escrito. **É o único
  lugar do backend com os nomes dos provedores — e isso agora é teste, não
  disciplina**: um `ast` percorre `operax/` e `server/` e reprova qualquer
  literal fora da matriz (a exceção é o docstring de `provedores/base.py`).
- `GET /canais/conexoes` — a frase que o produto sabia dizer e não dizia:
  **qual** regra está bloqueada por **qual** template. As contagens vêm de
  `fn_whatsapp_readiness`, a lista da rota, e **as duas leituras não são
  fechadas por definição**: divergência entre elas é deriva de predicado e vai
  para o log com tenant e os dois números, nos dois sentidos.
- `outbox.py` e `sender.py` passaram a derivar a lista de provedores da matriz.
  Há teste de igualdade de conjunto **nos dois sentidos** contra o predicado do
  índice `integration_whatsapp_unico_ativo` e contra a CTE da função — um nome a
  menos na lista é um cliente para quem `enqueue` grava a fila com provedor nulo
  e o sender descarta: nenhum alerta, sem exceção. É exatamente a edição que o
  C3 vai fazer nessa tupla.

**Os dois ALTOs do ciclo 1 eram na esteira de alertas, e são a lição da sprint.**
O implementador trocou `provider in (...)` por `provider = any(%(lista)s)`, e o
`list()` que embrulhava a tupla era load-bearing — sem ele, `malformed array
literal` no psycopg real. **Nenhum teste ligava o parâmetro**: `enqueue` não tem
pytest, e o `93` só compila a instrução. A esteira quebraria em produção com 667
verdes. Voltou à forma original, com o literal **renderizado em import time** a
partir da matriz; o `93` compila o texto que roda de fato.

📌 **Sete de nove mutações do revisor sobreviveram no ciclo 1, todas do mesmo
tipo:** teste cujo docstring afirma o que a asserção não mede. O pior: um
docstring dizia que o `98` provava o predicado contra Postgres — e o `98` nem
menciona as tabelas. Agora `_BLOCKED_SQL` **executa** no banco de ensaio, com
os três formatos nulos nomeados um a um e o positivo do par (aprovar o template
tira uma regra da conta; desligar as outras duas leva `ready` a `true`).

**Dois desvios de contrato, os dois certos e declarados:** `template_code` e
`meta_status` são anuláveis, porque a função conta como bloqueada a regra sem
template e a que cita código inexistente — a tela precisa distinguir os casos.
⚠️ A resposta **não** distingue "código inexistente" de "template inativo"
(ambos `meta_status null`); a frase da tela será a mesma para os dois.

⛔ **Uma correção de ordem neste documento:** o C1 listava *"aba de templates com
sincronização de `meta_status` a partir da WABA"*. **É impossível antes do C2** —
sincronizar exige token da Graph API, e o token só existe quando o C2 gravar
credencial. Movido para depois do C2. E `app.message_template` não tem escrita
por superfície nenhuma: até lá, um cliente não sai de `ready = false` pelo
painel.

**Um erro de despacho, meu:** a §1 mandava tirar o literal de `sender.py` e a
§3 mandava não tocar em `sender.py`. O implementador resolveu pelo lado que
preserva comportamento.

**O que o C1 backend NÃO fechou (dívida nomeada, não bloqueio):**
- ⏳ `conftest.py:last_migration_with` só é provado "último" pelo ritual da
  migration temporária; hoje índice e função têm uma definição só.
- ⏳ `order by` de `_BLOCKED_SQL` não é contrato; se a tela depender da ordem,
  prender.
- ✅ A metade de **frontend** do C1 (a tela de Conexões) — aprovada em 13/09,
  ver a seção abaixo.
- ⏳ Produção segue **sem canal**: `app.integration` só tem o Secullum; contato,
  regra e template em zero. A tela vai responder `provider: null` no primeiro
  dia — e é isso que ela tem a dizer.

### ✅ C1, metade de frontend — aprovada em 13/09/2026, um ciclo

**Ciclo 1: APROVADO** — zero ALTO, zero MÉDIO, sete BAIXO. Portões medidos por
mim: Vitest **42 arquivos / 675 testes** (baseline 38 / 638), prettier limpo,
`tsc` exit 0, lint com os três warnings pré-existentes de outros arquivos.

**O que entrou:** `dashboard/administracao/conexoes` (página), `components/canais/
connections.tsx` (os três blocos: canal, saúde, o que está preso),
`lib/canais/queries.ts` (Caminho 2, `GET /canais/conexoes`; 401/403 → `null`,
500 relança), `lib/canais/labels.ts` (o único arquivo de `src/` com o nome de
um provedor — e isso é teste que varre `src/`, não disciplina), `lib/canais/url.ts`,
e "Conexões" na navegação sob `showAdminWrites`.

**O gate da sprint está na tela e é teste:** tenant oficial com regra ligada
apontando para template `pending` mostra *"a regra **X** aponta para o template
**Y**, que está **pendente** na Meta"*. Os dois outros nulos do contrato têm frase
própria — e a do caso 2 diz *"não existe ou está inativo"* porque a API não
distingue, e a tela não finge que distingue.

**Doutrina da SPEC §1 presa por duas trancas independentes:** a frase do que o
canal exige vem de `capabilities`, nunca do nome. O revisor refez a mutação
`requires_templates: provider === "meta_cloud"` e ela morre pelos dois testes de
flags invertidas do componente **sozinhos**; a varredura de `labels.test.ts` é
a segunda tranca, não a única.

**Decisão declarada no despacho, não do implementador:** a página fecha por
`isAdmin`, mais estreita que a rota (que aceita qualquer membro do tenant). O
motivo: Conexões é configuração de canal, e o C2 põe a escrita de credencial
exatamente aqui — escrita que só o admin faz. Nav e página na mesma condição,
para não repetir o achado do S5 (porta aberta sem link). Medido pelo revisor:
um 403 na rota implica 403 no `/me`, então a página já respondeu 404 antes de
chamar a API — o `null` de `loadConnections` só sobra para 401 numa corrida de
milissegundos.

**Um arquivo fora da lista, aceito:** `lib/canais/url.ts` com `CONEXOES_PATH` —
toda rota do produto vive em `lib/<área>/url.ts`, e o shell importa de lá.

**Os sete BAIXOs, e o que foi feito com cada um.** Três sobreviveram a mutação e
eu fechei antes do commit, com a mutação refeita e morrendo: (1) o ramo
`capabilities: null` com `provider` preenchido não tinha teste — um fallback de
flags falsas leria "aceita tudo", o erro que a matriz existe para impedir;
(2) `ready && rules_blocked === 0` tinha uma metade morta por contrato
(`ready ⇒ rules_blocked = 0`) e sem teste — simplificado para `ready`, e o
docstring diz por que a tela confia; (3) o positivo da varredura só provava que
ela lia `labels.ts` — agora exige o componente, o arquivo mais provável de
ofender. **Os quatro restantes ficam nomeados:**
- ⏳ A frase do estado `null` da página (*"a API não respondeu agora"*) afirma
  uma causa que não é a real para 401; **copia `mapeamento/page.tsx`**, então
  corrigir é nas duas, fora desta sprint.
- ⏳ `<Requirements>` não tem frase para canal **sem nenhuma** das duas flags —
  hoje impossível pela matriz, e é **exatamente o Telegram** (SPEC §1.1). É o
  primeiro lugar que o C3 toca no frontend; silêncio ali seria a leitura "canal
  sem regra" que a SPEC chama de perigosa.
- ⏳ O critério 7 (não oficial sem "Meta") só cobre o estado real de hoje —
  para não oficial a função devolve `ready = true` e a rota nem consulta a
  lista.
- ⏳ O teste "sem tenant na URL" checa só a URL; basta para GET, não cobriria
  corpo de POST.

## C2 — Escrita de credencial pelo Caminho 2

- `POST` que **valida e só então grava**; valor no Vault, ponteiro em
  `app.integration_secret`.
- `GET` devolve `{ configurado, atualizado_em, identificacao_publica }`.

⛔ **Parada obrigatória:** primeira escrita de credencial pelo painel.

**Gate — três, e o terceiro é o que costuma escapar:**

1. credencial inválida **não grava nada** — a linha do Vault não aparece;
2. nenhum `GET` devolve o segredo, em nenhum campo, em nenhum estado;
3. **o token não aparece no log nem na mensagem de erro** — teste que provoca
   falha no provedor e varre a saída de log procurando o valor. Provedor que
   ecoa o token no corpo do erro é o caso real; descartar o corpo é a defesa.

### ✅ C2, metade de backend — aprovada em 14/09/2026, dois ciclos; guardião PASSA em 15/09

**Ciclo 1: REPROVADO** (1 ALTO, 2 MÉDIO, 12 BAIXO). **Ciclo 2: APROVADO.**
Portões medidos por mim: pytest **745** (baseline 675), ruff limpo, `db-test`
`SUÍTE COMPLETA OK` com 64 asserções do bloco de canais contra o cofre real.

**O que entrou:**
- `backend/operax/core/vault.py` — o cofre por tenant, que o `CLAUDE.md` listava
  e ninguém tinha escrito. `store_secret` cria ou atualiza (o nome no cofre é
  determinístico por ponteiro; regravar não duplica — contado em
  `vault.secrets`) **na transação do chamador**; `read_secret` só tem
  consumidor no `97` — é do C5. Toda instrução liga `%(tenant_id)s` pelo `join`
  com `app.integration`, porque a tabela de ponteiros não tem `tenant_id`.
- `alertas/provedores/{meta_cloud,z_api,uazapi}.py` — **só a verificação**;
  `enviar` continua sendo o C5. Cada módulo declara o formulário **como dados**
  (`FieldSpec`: `pattern`, `autocomplete`, `inputmode`, `secret`, `hint`) — o
  §5.4 num lugar só — e `verify(fields, http) -> str` devolve a identidade
  legível. Falha é `InvalidCredentialError(code)`, levantada `from None`:
  nunca corpo, nunca URL.
- `GET /canais/provedores`, `GET /canais/credencial`, `POST /canais/credencial`
  — a ordem do `POST` é a de `curadoria.py`: `util.is_admin` no `user_scope`;
  formato de cada campo **antes** de qualquer HTTP; o provedor **fora** de
  transação; uma transação de `service_role` que desliga o WhatsApp ativo,
  faz upsert de `app.integration` (`alias = provider`, como o `secullum` de
  produção), um segredo no cofre por campo secreto, e `audit_log` com as
  **chaves**. `config` e as chaves do cofre são **derivados de
  `FieldSpec.secret` na rota** — virar a flag move o campo de um lugar para o
  outro, e há teste de partição por provedor.
- Um handler de `RequestValidationError` em `server/main.py`, **fora das
  entregas e aceito**: o 422 nativo do FastAPI devolvia o corpo inteiro em
  `input` — token de volta na resposta antes de a rota rodar. Vale para RH e
  DP pelo mesmo caminho.

**Os três gates da SPEC §5, medidos:** (1) credencial inválida não grava —
a transação nem abre; (2) nenhum `GET` devolve valor nem `vault_id` — a
consulta real executada no ensaio, colunas afirmadas; (3) **o token não
aparece no log nem no erro** — e o caso real é o `z_api`, que leva o token
**no caminho da URL**: o `httpx` loga a URL inteira em INFO e a
`HTTPStatusError` a carrega na mensagem. Duas defesas, as duas provadas por
mutação: o logger do `httpx` silenciado onde o cliente nasce, e `from None`
em toda recusa. O revisor escreveu um gate 3 próprio para os três provedores
e, sem a defesa, o token apareceu na linha exata do `httpx`.

📌 **O ALTO do ciclo 1 é a lição desta sprint:** `str(Jsonb(...))` do psycopg
**trunca em 35 caracteres**. A "varredura inteira" dos parâmetros da transação
não via dentro de `config`, `antes` nem `depois` — o token gravado na
auditoria passava por 735 verdes e pelo `db-test`. Agora a varredura abre
`Jsonb.obj` (mapeamentos, listas, chaves), e há uma sentinela que reprova o
próprio harness se ele voltar a `str()`. E um segundo furo achado pelo
implementador no caminho: uma asserção nova do `97` estava **dentro** do
`begin … exception when others` da prova de atomicidade e era engolida — o
sub-bloco passou a capturar só a falha injetada, por SQLSTATE próprio.

**Premissas, não medições (a parada do dono é onde se descobrem):** os três
endpoints de verificação. Endpoint errado falha para o lado seguro:
`unauthorized`/`malformed`, nada gravado.

**Guardião de superfície, dez de dez, medido em 15/09:** dicionário idêntico
(nenhum objeto novo em `public`); `vault` sem grant nem privilégio de schema
para `anon`/`authenticated`, e nenhuma view de `public` nem função de
`util` cita o cofre; `app.integration_secret` sem policy, RLS ligada, e o
**owner** do tenant toma `permission denied` ao ler — na mesma transação em
que lê `app.integration`; o `GET` real devolve só `provider`, `public_identity`
e `updated_at`, com o valor comprovado no cofre; ciphertext ≠ valor e
`decrypted_secret` = valor; gate 3 sob `DEBUG` com zero ocorrências do token
e, sem a defesa, o mesmo transporte loga a URL; 422 de RH e DP sem `input`
(e com o handler padrão os três ecoam CPF e salário); nenhum literal de
segredo fora de stub de teste; `.env` intocado. Duas notas que não mudam o
veredito: o grep literal `HTTP Request:` é ambíguo com o `httpx2` do
`TestClient` (filtrar por `^INFO +httpx:`), e o handler preserva `ctx` — um
`field_validator` que interpole valor no `ValueError` reabre o eco por outra
porta.

**Dívida nomeada:** `base_url` do `uazapi` é host arbitrário (SSRF cego —
`https` só, 10 s, corpo descartado, admin do tenant; denylist de faixas
privadas é decisão futura); `setLevel` do `httpx` é global ao processo; o
`97` não varre `config` (quem prende é o pytest com `.obj`); o scanner por
`ast` de códigos de recusa só vê literal; `responses={422:…}` fora do OpenAPI;
`Mapping[str, ModuleType]` sem `Protocol` até o C5; `updated_at` do ponteiro
ao regravar sem asserção (`now()` é constante na transação).

### ✅ C2, metade de frontend — aprovada em 15/09/2026, um ciclo

O contrato (`ProviderForm`, `FieldForm`, `CredentialStatus`, `CredentialRequest`)
está fixado em `models.py` e o ciclo de correção do backend não muda a forma —
por isso as duas metades correram juntas, em arquivos disjuntos. **§5.4 foi o
gate desta metade:** o formulário é dirigido pelos dados de
`GET /canais/provedores` (`autocomplete`, `inputmode`, `pattern`, `secret`,
`hint` vêm da API), a validação Zod usa o mesmo `pattern` que o backend impõe,
ancorado como o `fullmatch` de lá, e o segredo nunca volta — campos secretos
limpos após sucesso.

**O que entrou:** `components/canais/credential-form.tsx` (um `useForm` por
provedor, remontado pelo `key` na troca; `secret` decide `type="password"`;
`<Requirements>` compartilhado com a tela, pelas flags); `lib/canais/queries.ts`
ganha `loadCredential` e `loadProviderForms` sobre um `readOrNull` só (401/403
→ `null`, 500 relança); a página de Conexões carrega as três leituras em
paralelo e renderiza o formulário abaixo do diagnóstico.

**Revisão, ciclo 1: APROVADA** — Vitest **716** (baseline 675), prettier e
`tsc` limpos; 23 mutações aplicadas (8 do contrato + 15 do revisor), **zero
sobreviventes**; §5.3 varrido no DOM inteiro (`innerHTML`, `textContent`,
todo atributo de todo elemento, `.value` de todo `input`) após 200, após 422
e no erro de formato do próprio campo secreto: depois de gravar, o segredo
não está em lugar nenhum. Um MÉDIO corrigido antes do commit: a frase de
sucesso nunca era limpa — um 422 na tentativa seguinte a deixava ao lado do
alerta vermelho, e trocar o provedor a mantinha sobre o outro formulário.
Agora o desfecho do envio é um estado só (sucesso *ou* erro, nunca os dois),
zerado ao trocar de provedor, separado do que está gravado — que é fato e
segura o "Configurada" até o `refresh` trazer a prop nova. Duas mutações
próprias provam os dois testes novos.

**Decisão registrada:** a identidade pública aparece duas vezes logo após
gravar (no estado e na linha `role="status"`). Fica: a linha viva é o que a
tecnologia assistiva anuncia, e "conectado como …" é a confirmação que o
provedor deu — tirá-la dali silencia o anúncio para poupar uma repetição
visual.

**Achado do revisor que é do backend:** o navegador compila o atributo
`pattern` com a flag `v`, e `-` sem escape dentro de classe não compila nesse
dialeto — o atributo é descartado em silêncio (o form é `noValidate` e quem
valida é o Zod, então não há efeito de comportamento). Corrigido em commit
próprio, com o teste que prende o dialeto.

## C2b — Aba de templates: o catálogo, e o "Sincronizar" da WABA

O item que o C1 adiou para *"depois do C2"*, mais o que ele pressupõe e ninguém
tinha escrito: `app.message_template` está **vazia em produção** e **não tem
escrita por superfície nenhuma**. Sincronizar `meta_status` de uma tabela vazia
não tira ninguém de `ready = false`. Então a aba são duas coisas, e a segunda
não existe sem a primeira:

1. **O catálogo** — listar, criar e editar o template do tenant pelo Caminho 2:
   `code`, `category`, `language`, `variables`, `body`, `meta_template_name`,
   `active`. `meta_status` e `meta_rejection` **não são editáveis à mão**: quem
   os escreve é a sincronização. O gatilho `util.validate_template_body` continua
   sendo o juiz do corpo, e a mensagem dele é a que o operador vê.
2. **O "Sincronizar"** — `POST /canais/templates/sincronizar` lê o token da Cloud
   API do cofre (`read_secret`, o primeiro consumidor real), lista os templates
   da WABA na Graph API e traz `status` e `rejected_reason` para as linhas que
   têm `meta_template_name`. **Só `APPROVED` vira `approved`** — qualquer outro
   status, conhecido ou não, bloqueia. Template local sem par na WABA volta a
   `draft`, com a razão registrada em `meta_rejection`.

**Uma consequência no C2, e é por isso que ela entra aqui:** listar templates
exige o **id da WABA**, que o formulário do `meta_cloud` não pedia. `waba_id`
entra como campo não-secreto (§5.4, como dado), e a verificação do C2 passa a
conferir também que o token alcança essa WABA — validar antes de gravar (§5.2)
vale para o campo novo. A primeira credencial real ainda não foi gravada, então
não há linha para migrar.

⛔ **Sem parada do dono:** nenhuma migration, nenhuma policy, nenhum objeto em
`public`. Guardião obrigatório mesmo assim — `core/vault.py` é tocado.

**Premissas, não medições:** `GET /v21.0/{waba_id}/message_templates?fields=name,status,language,category,rejected_reason` com Bearer, paginado por `paging.next`; os status da Meta (`APPROVED`, `IN_APPEAL`, `PENDING`, `REJECTED`, `PENDING_DELETION`, `DELETED`, `DISABLED`, `PAUSED`, `LIMIT_EXCEEDED`). Endpoint errado falha para o lado seguro: nada muda de status e o operador vê a recusa.

**Gate — quatro, e o quarto é o que costuma escapar:**

1. quem não é admin do tenant não cria, não edita e não sincroniza — **e o admin
   cria** (o positivo);
2. corpo que não usa uma variável declarada é recusado **pelo gatilho**, e a
   frase do gatilho chega ao operador como `detail` — não uma cópia dela no
   Python;
3. da sincronização, **só `APPROVED` produz `approved`**; um status novo da Meta
   que ninguém previu não abre a entrega;
4. **o token não aparece no log nem no erro** da sincronização — o mesmo gate 3
   do C2, com a mesma varredura sob `DEBUG`.

### ✅ C2b, metade de backend — aprovada em 15/09/2026, um ciclo; guardião PASSA no mesmo dia

**O que entrou:**
- `waba_id` no formulário do `meta_cloud` (não-secreto, `[0-9]{5,32}`), e a
  verificação do C2 passou a fazer **duas** leituras com o mesmo Bearer — o
  número e `GET /{waba_id}?fields=id`. Token que alcança o número e não a WABA
  é `unauthorized`, nada gravado.
- `meta_cloud.list_templates` — `GET /{waba_id}/message_templates` paginado
  por `paging.next` com teto de 10 páginas, e o `next` só é seguido em
  `https://graph.facebook.com`: sem a checagem, o Bearer sairia nove vezes
  para um host que veio no corpo. `META_STATUS` como dado, nove status, e **só
  `APPROVED → approved`**.
- `GET /canais/templates` (como o usuário, sob RLS), `PUT /canais/templates/{code}`
  (admin; forma só do que o banco não confere; **um** upsert cujo `case … is
  distinct from` volta o status a `draft` quando `meta_template_name` muda; o
  `P0001` do gatilho vira 422 `template_body` com `diag.message_primary` — **zero
  `{{` no router**), `POST /canais/templates/sincronizar` (admin; a integração
  oficial e o token do cofre numa transação que **fecha antes** do HTTP; o
  mapa decide; **um** `update … from unnest` grava só o que mudou; uma linha de
  auditoria com `updated`/`unmatched`/`meta_total`). `read_secret` ganhou o
  primeiro consumidor real.

**Revisão, ciclo 1: APROVADA** — pytest **820** (baseline 749), ruff limpo,
`db-test` `SUÍTE COMPLETA OK` com o `97` compilando 13 instruções e o cenário
de templates contra o gatilho real e a RLS real; as seis instruções executadas
via psycopg contra o ensaio. Nenhuma mutação sobreviveu às duas suítes
juntas. Fechados antes do commit:
- **A corrida que o revisor achou:** um `PUT` que troca `meta_template_name`
  enquanto a Meta responde já pôs a linha em `draft`; gravar por `id` escreveria
  o veredito do nome velho sobre o nome novo. O nome entrou na chave do
  `update` (`and t.meta_template_name = v.name`), com teste no pytest (o stub
  vê estados diferentes no `select` e no `update`) e no `97` (grava 0, a linha
  segue `draft`).
- **O `97` não prendia o null-safe** do `is distinct from` da sync — `<>` no
  lugar passava inteiro, porque nenhum passo mudava só a razão de valor para
  nulo. Agora muda, e a mutação falha nomeada ("esperado 1, obtido 0").
- O 403 de template dizia "gravar a credencial"; tem frase própria.

**Guardião de superfície, dez de dez:** dicionário idêntico; `vault.py` mudou
só o docstring, e o cofre segue sem grant nem privilégio de schema para
`anon`/`authenticated`; a `_TEMPLATES_SQL` real sob RLS — owner de A vê os 2
dele e 0 de B, owner de B vê o 1 dele, `anon` toma `permission denied`, nas
**duas grafias de claim**; o `GET /canais/credencial` real com `waba_id` em
`config` continua devolvendo só `provider, public_identity, updated_at`; o token
da sync fora do log sob `DEBUG` (e o positivo: sem a defesa, a URL com o token
aparece); as três auditorias reexecutadas com os params exatos da rota, sem
segredo; o `paging.next` recusado em seis variantes hostis com uma requisição
só, e a checagem é `scheme == https and host == graph.facebook.com`, não
`startswith`.

**Dívida nomeada:** `diag.message_primary` é preso contra o driver só por
medição manual (duas, idênticas) — o `97` roda por `psql` e a suíte de banco
não tem psycopg; a costura é semântica da libpq, não deste código.
`VERIFY_TIMEOUT_SECONDS × MAX_PAGES` = até 100 s atrás de um botão. A grafia de
`language` (`pt_BR`) e a checagem de host do `next` são premissas sobre a Meta
— as duas falham para o lado seguro. Sentry e variáveis locais (herdada do C2;
`sentry_sdk` não é dependência hoje). `variables` que o ciclo não sabe
responder só é descoberto no `outbox`, no enfileiramento.

### ✅ C2b, metade de frontend — aprovada em 15/09/2026, um ciclo

O contrato (`TemplateRow`, `TemplateWrite`, `TemplateSyncResult`) foi fixado no
despacho; as duas metades correram em arquivos disjuntos, como no C2.

**O que entrou:** a página `administracao/templates` no molde de Conexões
(`isAdmin` → 404 antes de qualquer leitura; `loadTemplates` e
`loadConnections` em paralelo); `components/canais/template-catalog.tsx` — a
lista com badge por `meta_status`, o formulário de criar/editar com **um input
por variável** e a ajuda `{{n}}` viva lida da ordem deles, `meta_template_name`
com a nota do rascunho, e **nenhum input** para `meta_status`/`meta_rejection`;
o Zod só de forma (zero regra de `{{n}}` — quem recusa o corpo é o gatilho do
banco, e a frase dele é mostrada como veio); "Sincronizar com a Meta" **pelas
flags** (`requires_templates`), nunca por nome; o item "Templates" na navegação
e o link "ver templates" em cada regra presa de Conexões. Vazio em branco vai
como `null` — o backend recusa `""`.

**Revisão, ciclo 1: APROVADA** — Vitest **777** (baseline 716), prettier, `tsc`
e lint limpos; 12/12 mutações obrigatórias mortas (mais 15 variantes). Dois
MÉDIOs de cobertura fechados antes do commit, com as mutações que sobreviviam
reaplicadas e mortas: o item "Templates" na sidebar não tinha tranca (aparecer
para `executive` ou `unit_supervisor`, ou sumir, passava 11/11) e o link "ver
templates" não tinha teste. E um BAIXO: o `aria-describedby` do corpo apontava
só para a ajuda, nunca para a frase de erro.

**Decisão registrada pelo implementador, aceita:** sem cópia local da lista
após gravar — a linha vem pelo `router.refresh()`, porque uma sincronização no
meio deixaria a cópia mais velha que a prop (a tela diria `draft` onde o banco
já diz `approved`).

## C3 — Telegram como quarto provedor

- Migrations `ch_telegram_provider`, `ch_messaging_identity`, `ch_channel_health`,
  `ch_readiness_fn`, `ch_adhesion_fn`.
- `telegram` na matriz de capabilities, com `requiresRecipientOptIn: true`.
- Sender: render de `message_template.body`, mesmo caminho de `z_api`/`uazapi`.
- Webhook `/start` com segredo no header e caminho rotativo.
- Vigia de saúde — **que não religa**.

⛔ **Paradas obrigatórias:** duas tabelas novas em `app` com policy de RLS; e um
endpoint público sem autenticação de usuário.

**Gate:**

- as **oito** linhas da SPEC §2.2 viram `scripts/86_teste_canais_exclusividade.sql`,
  e a linha 1 (os dois canais coexistindo) é a que não pode passar por revisão de
  código — só o índice real responde;
- o mesmo alerta sai por WhatsApp e por Telegram com **texto idêntico**, a partir
  de um template só;
- `/start` com token inválido, expirado ou já usado **não vincula**, e as três
  recusas são distinguíveis no log;
- requisição no webhook sem o header secreto é descartada **antes** do parse;
- derrubar o bot e rodar o vigia muda o status e **não** tenta reconectar.

### ✅ As duas paradas foram abertas pelo dono em 15/09/2026

Autorizado como proposto, item a item:

1. **`app.messaging_identity` e `app.messaging_invite` sem policy** para
   `authenticated` — a régua de `app.integration_secret`: `revoke all` de
   `anon`/`authenticated`, `grant select, insert, update` a `service_role`
   (sem `delete`: revogar é `revoked_at`), RLS ligada, **nenhuma policy**.
   Nenhum papel do painel lê o `chat_id`, nem owner. O que a tela precisa vem
   de `public.fn_telegram_adhesion`, `security definer` recortada por
   `util.user_tenants()`, contagem por unidade, `grant execute` escrito.
   `app.channel_health`: leitura `util.has_tenant`, escrita só `service_role`.
2. **O webhook** como a SPEC §6: `POST /webhooks/telegram/{path_token}`,
   `path_token` rotativo por integração (desconectar rotaciona), header
   `X-Telegram-Bot-Api-Secret-Token` em comparação de tempo constante **antes
   de qualquer parse** (sem ele, 404 seco), rate limit por IP e por token, só
   `/start <token>`, nenhum eco do corpo em log ou erro.
3. **Bot por tenant** (SPEC §10.1).
4. **Convite válido por 7 dias** (SPEC §10.2).

A autorização vale sob estas premissas (Regra 0). Nada disso é `db push`:
aplicar em produção é outra autorização, com a ordem própria.

### ✅ C3, onda 1 — o banco — aprovada em 15/09/2026, dois ciclos; guardião PASSA

**O que entrou:** as cinco migrations da SPEC §4 (`20260915200001..05_ch_*`):
`telegram` nos três checks e o índice irmão `integration_telegram_unico_ativo`
(o de WhatsApp intacto); `app.messaging_identity` e `app.messaging_invite`
como a §3 as escreve, mais três índices parciais em `revoked_at is null` (uma
vigente por titular; um `chat_id` vigente por tenant) e `expires_at` de 7 dias;
`app.channel_health` com `app.fn_record_channel_health` (o `status_changed_at`
só avança quando o status muda — a regra da §7 mora no SQL);
`public.fn_channel_readiness` (uma linha por integração ativa dos quatro
provedores; Telegram é `ready` só com saúde `connected`; `fn_whatsapp_readiness`
depreciada por `comment on`, não apagada) e `public.fn_telegram_adhesion`
(contagem por unidade, sem nome nem `chat_id`; `joined/pending/revoked` é
partição dos colaboradores ativos, e a função **não lê** `messaging_invite`).
`scripts/86_teste_canais_exclusividade.sql` com as oito linhas da §2.2, cada
recusa **nomeando a constraint**; `98`/`99` com `permission denied` explícito
para owner/DP/RH (e o positivo, `employee_pii`, na mesma transação). Python:
`telegram` na matriz com `requires_recipient_opt_in`, `CHANNEL_PROVIDERS`;
`WHATSAPP_PROVIDERS` inalterado.

**Ciclo 1: REPROVADA, retorno estreito** — migrations, `86` e `99` corretos;
três asserções faltavam no `98`, e a primeira era ALTO: `fn_channel_readiness`
dizendo "pronto" para um bot que o vigia nunca mediu passava verde em toda a
suíte, porque a semente gravava a saúde antes de qualquer asserção. **Ciclo
2:** as três entraram (bot sem saúde → `health_status` nulo e `not ready`;
`z_api` + `telegram` com regra apontando para template `draft` →
`rules_blocked = 0`; um `desligado` fora da soma), e as três mutações morrem
nomeadas. Guardião dez de dez: coexistência **inserida** de verdade,
`service_role` sem `delete`, as duas RPCs executadas como owner sem o `chat_id`
de sonda na resposta, `fn_record_channel_health` fora do alcance do painel.

**Decisões registradas:** "convidado, aguardando" é coluna nova (`invited`) se
o C4 quiser — o `do $$` da migration 5 e o item 16 do `99` prendem o conjunto
exato de colunas. `alert_queue.channel`/`alert_rule.channel` continuam sem
`'telegram'` — é a representação do roteamento da §8, decisão da onda 2/C5.
`fn_record_channel_health` grava `detail` literalmente: "nunca corpo do
provedor" é dever do chamador, e a onda 2 precisa do teste. FKs de titular sem
par `tenant_id` (estilo da base; registrado).

### ✅ C3, onda 2a — provedor, credencial por canal, Conexões com dois canais — aprovada em 16/09/2026, um ciclo; guardião PASSA

**O que entrou:** `provedores/telegram.py` — `bot_token` como único campo
(secreto; o token vai no **caminho da URL** da Bot API, o caso do `z_api` de
novo: `verification_client()` e `from None`), `verify` por `getMe` → `@bot`,
`set_webhook`/`delete_webhook`/`webhook_info` com `last_error_message`
**mascarada antes do corte** (ela pode ecoar a URL do webhook, que carrega o
`path_token`); `429` é `unreachable`, não veredito sobre o token. Canal como
dado em `capacidades.py` (`channel_of`, `providers_of`); a credencial desliga
**só o canal** do provedor que entra — gravar o bot deixa o `meta_cloud` ativo,
e o `97` prova no banco (linha 1 da §2.2 pela porta da credencial);
`GET /canais/credencial?canal=`, `ProviderForm.channel`, `CredentialStatus.channel`.
`GET /canais/conexoes` lê `fn_channel_readiness` e devolve `{whatsapp, telegram}`
(o estado do bot — `public_identity`, `webhook_url`, `webhook_path_token`,
saúde — sai por `tenant_scope` com o tenant ligado, porque `app.integration` só
tem policy de admin e um supervisor veria a função e não o bot). `POST
/canais/telegram/conectar` (**grava → fecha a transação → `setWebhook`**; recusa
deixa `disconnected` com frase própria, nunca corpo do provedor) e
`/desconectar` (`deleteWebhook` **antes** de qualquer escrita; recusa → nada
muda; sucesso **rotaciona** o `path_token` e o segredo). `API_PUBLIC_URL`
opcional em `config.py` — presente, exige `https://` sem barra final, ou o
processo não sobe.

**Revisão, ciclo 1: APROVADA COM BLOQUEIO DE BANCO** (o Docker estava fora; a
suíte rodou verde depois — `97` com 16 instruções + 2 renderizações do bot e o
cenário "o bot, com os dois canais ativos lado a lado"). pytest **889**
(baseline 822). 20 mutações, 19 mortas no pytest e a vigésima morta só pelo
`97` (a lista exata de colunas de `_TELEGRAM_STATE_SQL`). Fechados antes do
commit: **regravar o token do bot com webhook registrado** apagava
`webhook_url` do `config` e deixava a saúde em `connected` — a tela diria
"pronto" ao lado de "Conectar bot", com o Telegram entregando num caminho que
o banco não conhece mais; agora a mesma transação grava `disconnected` com
"token do bot regravado; conecte o bot de novo" (e regravar o WhatsApp não
toca a saúde do bot). Mais três BAIXOs: a asserção que mata a vigésima
mutação no pytest, o fixture da máscara com a URL atravessando a posição 200,
e o `429`.

**Guardião, dez de dez:** o token do bot aparece no log **uma** vez — na
metade de controle do teste que exige o vazamento com o cliente cru antes de
exigir a ausência com a defesa; o `webhook_secret` está no cofre (ciphertext ≠
valor, lido de volta pela chave) e em lugar nenhum do `config`, do estado, da
auditoria ou do log; a `_TELEGRAM_STATE_SQL` real devolve seis chaves exatas
sem `bot_token`/`webhook_secret`; `_RECORD_HEALTH_SQL` ligada ao outro tenant
não avalia a função; `API_PUBLIC_URL` inválida derruba o processo sem
imprimir o valor; a desativação por canal deixa o outro canal ativo com a
linha do bot no lugar (`active = false`, sem delete).

**Ação do dono pendente:** `API_PUBLIC_URL` no painel do Railway (`operax-api`) —
`https`, sem barra final; hoje a URL do Railway, porque `api.fastparks.com.br`
não resolve. Sem ela, "Conectar bot" responde 422 `no_public_url` e nada é
registrado, de propósito.

**Decisões registradas:** `webhook_url`/`webhook_path_token` visíveis a qualquer
membro em `GET /canais/conexoes` — a autenticação do webhook é o header
secreto, que a 2b tem de conferir **antes do parse** (senão o `path_token`
vira segredo e isto volta como achado). `deleteWebhook` recusado → nada muda
(rotacionar sem confirmação deixaria a plataforma entregando num caminho
morto com a tela dizendo "desconectado").

### ✅ C3, onda 2 — frontend — aprovada em 16/09/2026, um ciclo (1b)

**O que entrou:** a tela de Conexões com **dois cartões, sempre** — WhatsApp e
Telegram, cada um com o seu vazio, porque os canais coexistem (§2.1) e a tela
não pode sugerir que um substitui o outro; o cartão do Telegram com o
`bot_username` como título, saúde por `health_status` em quatro estados
(`connected`/`disconnected`/`unknown`/nunca medido) com *"desde …"* e
*"conferido em …"* no fuso do tenant, `health_detail`, e o endereço do webhook
**como o backend o registrou** (`webhook_url` entrou no contrato; uma tela
que compusesse o endereço com `NEXT_PUBLIC_API_URL` cai em quatro testes);
`<Requirements>` com a terceira frase pela flag `requires_recipient_opt_in` e
a frase de "sem restrição declarada" (a dívida do C1); `telegram-connection.tsx`
com "Conectar bot"/"Desconectar" para admin — **nenhum "reconectar" em nenhum
estado** (§7), com teste negativo; dois `<CredentialForm>`, um por canal,
filtrados por `channel` e nunca por nome. `Channel`, `CHANNELS` e
`CHANNEL_LABEL` nasceram em `labels.ts` para que **nenhum** outro arquivo de
`src/` escreva `"telegram"` — a varredura passou a caçar o quarto nome entre
aspas (a regra da §1.1 ao pé da letra), sem afrouxar o `\b` dos três de
WhatsApp.

**Uma correção aceita fora da lista:** `useId` em `credential-form.tsx` (3
linhas) — dois formulários na mesma página com um campo de mesmo nome
gerariam dois `id` iguais, e o `<label for>` do segundo apontaria para o
primeiro. É defeito que a instanciação dupla cria, não excesso de escopo.

**Revisão, ciclo 1: APROVADA** — Vitest **837** (baseline 777), prettier,
`tsc` e lint limpos; 14/14 mutações obrigatórias mortas. Três MÉDIOs de rede
de teste fechados antes do commit (docstrings que afirmavam mais do que a
asserção media: o catálogo caindo no primeiro canal preenchido, o badge
oficial do bot fixo, `health_detail` escondido quando `connected` — o produto
estava certo nos três, e agora as mutações morrem), e um BAIXO de
acessibilidade: o "copiado" do botão de copiar não chegava ao leitor de tela,
porque o `aria-label` fixo é o nome do botão — ganhou região viva própria,
que só existe quando há desfecho.

### ✅ C3, onda 2b — o webhook `/start`, o vigia, o `enviar` — aprovada em 16/09/2026, um ciclo; guardião PASSA

**O que entrou:** `context_for_webhook` em `core/tenant.py` — o **segundo** SQL
sancionado a atravessar tenants (quem chama é o Telegram, sem tenant; a
cauda rotativa da URL é o único jeito de saber qual), de tenant **ativo**, e
um teste enumera exatamente os três SQL de `tenant.py` que atravessam.
`POST /webhooks/telegram/{path_token}` fora do OpenAPI, sem JWT, com a
**ordem como contrato**: rate limit por IP → resolução (forma do token antes
do banco; desconhecido → 404 seco e um contador, nenhum log) → rate limit por
token → header `X-Telegram-Bot-Api-Secret-Token` contra o cofre por
`hmac.compare_digest` **antes de ler o corpo** (errado → 404, não 401: não se
confirma o endpoint a quem não tem o segredo) → só então o parse:
`chat.type == 'private'` obrigatório (um `/start` num grupo traria o `chat_id`
do grupo, e o alerta individual iria ao grupo pela porta que
`validate_alert_target` não vigia — regra 7), `/start <token>`, e tudo o mais
é 200 vazio com o **tipo** no log, nunca o texto, nunca o `chat_id`. A adesão:
`sha256` do token, `for update`, três recusas distinguíveis no log
(`invite_unknown`/`invite_used`/`invite_expired`) com o convite intacto;
válida → consome, **revoga a vigente anterior do mesmo titular** (`novo /start`),
insere, audita sem `chat_id`; `chat_id` já de outra pessoa → `chat_in_use`
pelo índice, e a subtransação desfaz o consumo. `RateLimiter` movido para
`server/ratelimit.py` com chave genérica, o assistente inalterado. O vigia
(`python -m operax.alertas.vigia`) pergunta `getWebhookInfo` fora de
transação e grava por `alertas/saude.py`: `connected`, ou `disconnected` com
frase **sua** (webhook ausente / apontando para outro endereço / erro de
entrega nas últimas 24 h / updates acumulados), ou `unknown` — e **não nomeia
`set_webhook`**. `TelegramProvider.enviar`: `sendMessage` com
`render(body, message)`, sem `parse_mode`, 403 → `blocked` sem revogar nada
(é o C4 quem revoga); `Message.body` opcional, `sender.py` intacto.

pytest **990** (baseline 889); suíte de banco verde com o `97` compilando 25
instruções e a quinta parte — o webhook, 49 asserções contra o banco real
(resolução por `path_token`, `/start` válido/expirado/usado, `chat_in_use`
nomeado pelo índice, a segunda adesão revogando a primeira).

**Revisão, ciclo 1: APROVADA** — 37 mutações, 35 mortas, mais duas medições
do revisor contra banco e cofre **reais** (o `_bind` do webhook por psycopg,
26/26; a app inteira fim a fim, 19/19). Fechados antes do commit os três
MÉDIOs: o vigia afirmava "HTTP com a transação fechada" sem asserção (a
linha do tempo passou a ver o `http` entre os dois escopos, e a mutação que
o move para dentro morre); "sem segredo no cofre" era testado só **com**
header — sem header, `compare_digest(b"", b"")` é verdadeiro, e um `secret or
""` antes da comparação abriria o endpoint a quem não manda header nenhum
(agora parametrizado, e a mutação morre); e o limitador nunca despejava
chaves — 50 mil IPs eram 50 mil entradas para sempre (chave que envelheceu
inteira sai do mapa, com teste). Mais o `RecursionError` de JSON aninhado até
o limite, que virava 500 em vez de "corpo inválido". **Guardião dez de dez:**
404 seco em token inventado e em header errado, 200 vazio com corpo lixo,
fora do OpenAPI, `GET` 405; 47 registros do webhook em `DEBUG` dizendo só o
tipo e nenhum com `chat_id`; auditoria com `invite_id` e `channel` e nada
mais; o único caminho novo que atravessa tenants é `context_for_webhook`, e
tenant inativo com token válido devolve zero; `set_webhook` ausente do vigia
em código.

**Lição de processo (memória):** o revisor mutou a árvore compartilhada
enquanto o guardião media; o gate só não fotografou o mutante porque tirou
hash antes e depois de cada item. Daqui em diante, mutação só em cópia.

**Duas ações do dono que esta onda cria:** agendar o vigia como terceiro
cron no Railway (mesma branch e root, variáveis por referência ao
`operax-api`, `python -m operax.alertas.vigia`, sugestão `*/15 * * * *` —
sem ele, `connected` é afirmação sem idade) e o `API_PUBLIC_URL` pendente da
2a. **Detalhe de deploy:** atrás do proxy do Railway `request.client.host` é
o IP do edge salvo `FORWARDED_ALLOW_IPS` — o limitador por IP fica global
(300/min); hoje há um tenant, e o de token (120/min) é o que separa.

**Premissas, não medições:** a forma do update real (`/start <token>`,
`chat.type`, `chat.id`); o Telegram limita o `start` a 64 caracteres, e o C4
deve gerar tokens ≤ 64; a URL que `getWebhookInfo` devolve é comparada como
string — se a plataforma normalizar, um webhook certo fica `disconnected` até
alguém medir o primeiro real.

### ✅ C3 fechado no código em 16/09/2026 — quatro commits, dez gates

`b629fb5` (banco), `25a9d35` (frontend), `04d9efe` (provedor, credencial por
canal, conectar/desconectar), `1584e22` (webhook, vigia, `enviar`). Cada
onda com revisor independente; as três de backend com guardião dez de dez.
pytest 822 → **993**; Vitest 777 → **837**; suíte de banco com 58 migrations,
o `86` e o `97` com 25 instruções compiladas contra o banco real.

**O gate do C3, item a item:** as oito linhas da §2.2 → `scripts/86_…`, cada
recusa nomeando a constraint ✅; `/start` inválido, expirado ou usado não
vincula, e as três recusas são distinguíveis no log ✅; requisição sem o
header secreto descartada **antes** do parse ✅ (e sem header também, presa
por mutação); derrubar o bot e rodar o vigia muda o status e **não**
reconecta ✅. O quinto — *"o mesmo alerta sai por WhatsApp e por Telegram com
texto idêntico, a partir de um template só"* — está **meio**: o `enviar` do
Telegram renderiza `render(body, message)` byte a byte, e é a mesma função
que `z_api`/`uazapi` vão usar; mas o `enviar` deles é o C5, e é lá que o
gate fecha inteiro.

**Nada disto está em produção.** O que depende do dono, na ordem:
1. push dos quatro commits (o último empurrado é `def9450`);
2. as cinco migrations da onda 1 em produção — autorização própria, com a
   ordem: captura datada → push → captura → diff;
3. `API_PUBLIC_URL` no `operax-api` e o cron do vigia (`python -m
   operax.alertas.vigia`, `*/15 * * * *`) no Railway; decidir
   `FORWARDED_ALLOW_IPS` (sem ele o limitador por IP é global);
4. `vercel promote` — o painel de produção ainda está em `78892f0`, sem a aba
   de templates e sem os dois canais;
5. as duas paradas de campo que ficaram para depois: a primeira credencial
   real pelo painel (C2) e o primeiro `getWebhookInfo` real (a comparação da
   URL é por string).

**Decisões que o C4/C5 herdam:** adesão voluntária ou esperada (SPEC §10.3);
o token do convite ≤ 64 caracteres (limite do `start` do Telegram); a
representação do roteamento — `alert_rule.channel`/`alert_queue.channel` não
têm `'telegram'`, e `channel='whatsapp'` com `provider='telegram'` é
contraditório; `invited` como coluna nova da adesão, se quiserem "convidado,
aguardando"; a confirmação ao usuário depois do `/start` (o bot não conversa;
se houver, é template).

## C4 — Adesão

**Isolado de propósito, e não bloqueia nada.** É projeto de campo, não código:
o C3 entrega o mecanismo completo e funcionando para quem já aderiu.

- Geração de convite, `token_hash`, validade, uso único.
- Envio do convite **por WhatsApp, para o número que já está em cadastro**
  (SPEC §3.3, regra 4) — é o que faz o vínculo herdar a confiança do cadastro.
- `public.fn_telegram_adhesion`: aderiram / faltam / revogaram, por unidade.
- Ficha mostra *"Telegram vinculado em DD/MM"* com botão de desvincular.

⛔ **A §3.3 é uma peça só.** Cortar uma das cinco regras por prazo é decisão de
owner com o risco escrito, nunca simplificação de implementação.

**Gate:** convite encaminhado a outra pessoa e clicado por ela **não** vincula
depois do primeiro uso; desvincular volta o destinatário para WhatsApp sem
perder o histórico; o painel de adesão não mostra nome nem `chat_id`.

### ✅ Decisão do dono, 16/09/2026: a adesão é **voluntária**

Consequências: o convite convida, não cobra; não há lembrete, reenvio
automático, prazo de resposta nem estado de cobrança; "faltam" vira "não
aderiram" — um número, não uma pendência. Quem não adere continua no
WhatsApp, e nada acontece.

### ✅ C4, backend — o convite pela fila de WhatsApp, o vínculo na ficha — fechado em 16/09/2026 (`f1f0774`)

Entregue com pytest **993 → 1062** (69 novos em `tests/test_canais_convites.py`),
ruff limpo, suíte de banco `SUÍTE COMPLETA OK` (o `97` compila 23 instruções
de `canais.py` + 3 de `outbox.py`; sexta parte com 66 asserções; `98`/`99`
intactos). Sem migration, sem HTTP, nada contra produção. As três rotas
entraram em `canais.py` (não num `adesao.py`: os helpers já estavam lá).

- `POST /canais/telegram/convites`: os seis passos na ordem; **nenhuma escrita
  antes das quatro condições** (provado pela lista de instruções); os SQLs
  da fila (`_ENQUEUE_SQL`, `_PROVIDER_SQL`, `_TEMPLATE_SQL`) e o da revogação
  (`webhooks._REVOKE_PREVIOUS_SQL`) são **importados**, não copiados. Token
  `token_urlsafe(32)` (43 ≤ 64), só o hash na tabela, o link só em
  `alert_queue.payload`. Resposta, auditoria e log sem token, link ou número.
- Duas decisões além do despacho, aceitas: a rota exige que o template
  declare **exatamente** `{nome, link}` (o gatilho só confere payload ⊇
  variáveis — um template sem `link` passaria nele e o convite sairia sem
  link); e a recusa do gatilho vira 422 **`invite_refused`** com a frase dele
  (sem isso, `meta_cloud` com template em `draft` daria 500). Sétimo código;
  o frontend mostra `detail` para código desconhecido.
- `GET …/vinculos/{id}`: quem vê o colaborador (`util.can_see_employee`, como
  o usuário; senão 404); `_LINK_SQL` em três subconsultas escalares, **sem
  `external_id`** (asserção textual no pytest e no `97`). `revogar`: admin,
  409 `not_linked`, `revoked_at` + razão, convites em aberto expiram junto.
- Premissas registradas: o número é lido em `tenant_scope` (é destino de
  entrega, não dado de tela — em `user_scope`, `pii_read` exigiria o domínio
  `pii`, que é "ver o CPF"); `queued` é sempre `true` num 200; o bot precisa
  estar **ativo com `@username`**, não conectado (o link vale 7 dias);
  colaborador desligado não é recusado; 10–11 dígitos são sempre Brasil.
- **Dívida do C5, reafirmada:** limpar `payload.link` ao marcar `sent`.
- O falso verde que nenhum teste pega: **o número certo da pessoa errada** —
  a confiança é herdada do cadastro (regra 4), e o cadastro errado vem junto.
  Mitigação: `destination_masked` mostra DDD e final antes; a ficha mostra o
  vínculo depois (regra 5).

**Guardião de superfície, 16/09/2026 — NÃO PASSA por um item, e o item é o
gate, não a rota.** 11 de 12 OK, zero janelas sujas (hash antes e depois de
cada item, 9 conferências). Nenhuma medição achou token, link, número inteiro
ou `chat_id` em resposta (a varredura de `resposta.text` procura os três e
ainda fixa o conjunto de chaves do JSON), auditoria (igualdade exata do
`depois` nos dois eventos), tabela (só o hash), log (nem com `httpx*`
forçado a nível 1, pela sonda do guardião) ou superfície pública (9 views,
12 RPCs, `messaging_*` sem policy e sem `d`, `alert_queue` sem leitor fora do
sender — o que dá peso à dívida do `payload.link`). **O que volta:**
`_app_log` em `test_canais_convites.py` descarta os registros `httpx*`/
`httpcore*` — herança do C3 — e a varredura sob `DEBUG` fica cega ao logger
por onde, no C5, a URL do provedor com o número vai passar. Uma linha:
varrer `caplog.records` inteiro, como `test_canais_credencial.py` já faz.

**Revisão (ciclo 1, mutação só em overlay): APROVADA.** 38 mutações, 36
mortas; as duas sobreviventes eram o mesmo furo — a borda de baixo da regra
"10–11 dígitos" (`_e164` aceitando 8 ou 9 passava nos 69 testes). O
revisor mediu o ponto de forma que eu tinha pedido: `_refuse` **devolve**,
não levanta, e `tenant_scope` comita na saída normal — então listou cada
`return _refuse` das três rotas com o que o antecede na transação:
nenhum vem depois de uma escrita (as quatro condições são só leitura; a
recusa do gatilho sai por exceção, que é rollback; o 409 do `revogar` é um
update de zero linhas). `util.validate_alert_template` interpola só código,
**nomes** de variáveis e status — nunca valor do payload —, então a frase de
`invite_refused` é segura. Premissa 2 sem achado: não existe admin que não
veja o colaborador (o primeiro ramo de `can_see_employee` é `is_admin`).

**Fechado por mim antes do commit:** a tabela do `_e164` ganhou 8 e 9
dígitos (e um caso de `invalid_phone`), provado no overlay do revisor que
as duas mutações morrem; `_app_log` varre todos os registros (o item do
guardião); asserção textual de `util.can_see_employee(e.id)` na instrução
(a mutação 3 morria por artefato do stub); as duas constantes do token que
só o teste usava saíram de `canais.py` (o padrão é `webhooks._START`); a
frase de `no_invite_template` cobre o template que existe com variável a
mais; a docstring de `InviteIssued.queued` diz que num 200 é sempre `true`.
**Registrado, não feito:** dois `POST` simultâneos para o mesmo titular não
se serializam (dois links válidos ao mesmo número) — o botão pendente fica
desabilitado na tela, e um lock por titular mudaria a contagem de
instruções que o `97` prende; entra se um dia aparecer.

Portões finais: pytest **1066**, ruff, `SUÍTE COMPLETA OK` (o `97` com as 23
instruções de `canais.py` recompiladas), dicionário sem deriva.

### ✅ C4, frontend — a ficha, o convite, a adesão por unidade — fechado em 16/09/2026 (`273dcb2`)

Entregue com Vitest **914 / 49** (+77), prettier, `tsc` e lint limpos (os 3
warnings pré-existentes, nenhum novo). Só `frontend/**`. `database.types.ts`
regenerado contra o `operax_test` (o `supabase db reset` não roda nesta
máquina): +25 linhas, exatamente `fn_channel_readiness` e
`fn_telegram_adhesion`, nenhuma tabela de `app`.

- `queries.ts`: `loadTelegramLink` (Caminho 2; **404 → `null`**, para a ficha
  cair em "Colaborador não encontrado" e não no error boundary) e
  `loadTelegramAdhesion` (Caminho 1, `rpc("fn_telegram_adhesion")` **sem
  argumento** — o gerador tipa `Args: never`, como em `fn_dp_alerts`).
- `telegram-link.tsx`: cartão "Telegram" abaixo das abas da ficha, não é aba.
  `linked` decide primeiro, depois `invite_open_until`; data nunca decide.
  Frase da adesão voluntária em **todos** os estados, inclusive `null`.
- `telegram-adhesion.tsx`: tabela Unidade · Aderiram · Não aderiram ·
  Revogaram · Total, com rodapé; dentro do cartão do Telegram, **só quando há
  bot**. Ordem: a da RPC (sem `order by` na função — sugestão para o C5).
- **Dispensado por mim neste ciclo:** o `Link` para Templates no 422
  `no_invite_template` — o despacho pedia o link e vedava `lib/api.ts`, e
  `ApiError` não carrega `code`. O `detail` da API já nomeia a aba. Patch
  aditivo proposto (`ApiError.code`), se um dia valer a pena: fica como
  dívida pequena, não como achado.

**Revisão (ciclo 1, mutação só em overlay): APROVADA.** 39 mutações, 36
mortas; as três sobreviventes eram nomes de teste afirmando mais do que a
asserção media — nenhuma era defeito de produto (o componente não guarda
cópia local, limpa o desfecho no clique, e o cartão vem depois das abas).
Fechei as três antes do commit e provei no overlay do revisor que cada uma
morre agora: o teste "sem cópia local" resolve o `revogar` com **outra**
data de revogação que a prop do refresh (a prop vence); o "erro antigo some"
afirma com a promessa ainda pendente; a posição do cartão é afirmada por
ordem no documento. Contrato conferido campo a campo contra `models.py` e a
migration 5; `rpc("fn_telegram_adhesion", {})` de fato não compila
(`Args: never`). Portões: Vitest **914 / 49**, prettier, `tsc`, lint com os
3 warnings de sempre.

O contrato (`InviteRequest`, `InviteIssued`, `TelegramLink`,
`fn_telegram_adhesion`) está fixado nos dois despachos. Sem migration: o
convite é uma linha de `app.alert_queue` sem regra, sob o mesmo contrato de
template (`telegram_invite`, variáveis `nome` e `link`), e quem entrega é o
sender quando o `enviar` de WhatsApp existir (C5) e o G4 fechar (regra 8).

### ✅ C4 fechado no código em 16/09/2026

Duas metades, dois revisores independentes com mutação em cópia (75
mutações, 72 mortas de primeira, as 5 sobreviventes fechadas e provadas
mortas antes do commit), um guardião de superfície com zero janelas sujas.
Sem migration, sem `db push`, sem HTTP, nada em produção. Commits
`273dcb2` (frontend) e `f1f0774` (backend).

**O que o C4 entrega quando o resto chegar:** o administrador abre a ficha,
vê "Não aderiu", clica "Convidar pelo WhatsApp", e a tela diz para que
número mascarado o convite foi; o link com o token fica na fila de
WhatsApp esperando o sender. Até o C5 existir e o G4 fechar, **nenhum
convite sai** — a linha fica `pending`, e é assim de propósito.

**O que fica para o dono (cada um pede o seu "autorizado"):** push dos
commits desde `def9450` (agora 7: os cinco do C3 e os dois do C4); as cinco
migrations do C3 em produção (captura datada → push → captura → diff — o
C4 não acrescentou nenhuma); `API_PUBLIC_URL` no `operax-api`; o cron do
vigia; `FORWARDED_ALLOW_IPS`; `vercel promote` (produção está em
`78892f0`); a primeira credencial real e o primeiro `getWebhookInfo` real.

**O que o C5 herda, nomeado:** o `enviar` de WhatsApp para `meta_cloud`,
`z_api` e `uazapi` (regra 11); o roteamento — Telegram se houver identidade
vigente, WhatsApp caso contrário; `app.alert_sent` por canal; **limpar
`payload.link` ao marcar `sent`** (o link com o token fica em
`alert_queue.payload` até lá, e `authenticated` tem `select` na tabela sob
`alert_queue_admin` — `app` não é exposto e nenhuma rota lê, mas é dívida
com nome); `alert_rule.channel`/`alert_queue.channel` sem `'telegram'`;
`order by u.name` em `fn_telegram_adhesion`; confirmação ao aderente depois
do `/start`, por template; exigir `connected` (e não só ativo) para emitir
convite, se o desenho quiser — é uma linha em `_bot_state`.

### Produção, 17/09/2026 — o que saiu com o "autorizo todos" e o que ficou

O dono autorizou os quatro itens de uma vez. Executado, na ordem em que a
premissa de cada um foi conferida:

- **Ledger de produção medido antes de tudo:** 64 registros, terminando em
  `38_alert_release`; as cinco `ch_*` são as únicas que faltam — a premissa da
  autorização das migrations está de pé.
- **Captura `2026-09-17T1131-antes-do-c3`** (`8fab825`): contra a de 08/09 a
  deriva é +115/-1 e **tudo é a 37 e a 38** — nada de terceiro em nove dias.
- **Push `def9450..8fab825`** (9 commits: C3, C4, captura). Railway subiu os
  três serviços; `/health` 200; as cinco rotas `/canais/telegram/*` no schema;
  webhook com path falso → 404 seco. **Consequência conhecida e aceita:** até
  as migrations entrarem, `GET /canais/conexoes` falha no SQL e o painel
  promovido (`78892f0`) mostra "As conexões não puderam ser lidas" — só isso.
- **`API_PUBLIC_URL`** gravada no `operax-api` (a URL do Railway, `https`, sem
  barra).
- **`operax-vigia`** criado: quarto serviço, mesma branch e root, variáveis
  por referência ao `operax-api`, `python -m operax.alertas.vigia`,
  `*/15 * * * *`, restart `NEVER`. Build do `8fab825` em SUCCESS.

**Ficou, e cada um tem o motivo:**

1. **As cinco migrations em produção — barradas pelo classificador do
   harness** ("Protected-Scope IaC Apply"), antes mesmo de montar os arquivos
   de aplicação. O caminho que funcionou para a 36 (Management API,
   transacional, com o `insert` no ledger na mesma chamada) é o mesmo; quem
   executa precisa da permissão. Os cinco arquivos estão em `supabase/
   migrations/20260915200001..05_ch_*.sql`; cada um vai numa chamada de
   `scripts/sb_sql.sh nklobmlxyidqxarzisph -f <arquivo>` com a linha
   `insert into supabase_migrations.schema_migrations (version, name) values
   ('<versão>', '<nome>');` no fim, na ordem 01→05; depois `python3
   scripts/capturar_producao.py nklobmlxyidqxarzisph --rotulo depois-do-c3`
   e o diff tem de ser só as cinco.
2. **`vercel promote` — segurado por mim até as migrations entrarem**, e não
   por falta de autorização: o painel novo chama `GET /canais/telegram/
   vinculos/{id}` na ficha de **todo** colaborador, e sem `app.messaging_identity`
   isso é 500 → a ficha inteira cai no error boundary. Promover antes do
   banco quebra a tela mais usada do RH.
3. **`FORWARDED_ALLOW_IPS` — barrada pelo classificador** ("Security Weaken").
   Minha recomendação, com o tradeoff: **`*`**. O contêiner só é alcançável
   pelo edge do Railway; sem a variável o limitador por IP do webhook é um
   balde global de 300/min, e qualquer um que bata em `/webhooks/telegram/
   qualquer-coisa` 300 vezes por minuto segura as entregas do Telegram de
   verdade (o IP é checado **antes** do token). Com `*`, um atacante que
   forje `X-Forwarded-For` consegue driblar o limitador por IP — e só ele; o
   de token (120/min) é o que separa. `*` é estritamente melhor contra o
   ataque ingênuo e igual contra o sofisticado.

## C5 — Roteamento e medição

- `Telegram se houver identidade vigente; WhatsApp caso contrário.`
- Entrega por canal em `app.alert_sent`.

### ✅ C5, onda 1 — fechada em 17/09/2026 (`a56732d` metade B, `524f786` metade A)

Contrato fixado antes do despacho, e já na árvore: `Message.language`
(`pt_BR`) e `Message.provider_template` (o `meta_template_name`), com defaults
— 131 testes de sender/outbox/provedores verdes sem mudança.

- **Metade A — roteamento, sender, medição:** duas migrations
  (`'telegram'` no check de `alert_queue.channel`; `fn_delivery_by_channel`
  em `public` + `order by` em `fn_telegram_adhesion`); `route` puro no outbox
  (identidade vigente **e** bot ativo → Telegram; senão WhatsApp; `email`
  intacto); o sender em **três fases com HTTP fora de transação**, que **não
  reserva com o gate aberto** (hoje ele reserva e queima os convites em
  cinco tentativas), passa `body`/`language`/`provider_template`, limpa
  `payload.link` em `sent` e `discarded`, e trata `blocked` revogando a
  identidade e re-roteando para WhatsApp. Guardião obrigatório.
- **Metade B — os três `enviar` de WhatsApp e a fábrica:** `meta_cloud`
  (template + parâmetros ordenados, nunca `render`), `z_api` e `uazapi`
  (`render(body, message)` local — o mesmo do Telegram); `fabrica.build`
  cobrindo os quatro pela matriz, sem literal novo; token e número em lugar
  nenhum de erro/log, `httpx` incluído.
- **Onda 2 (frontend) — despachada em 17/09/2026, em paralelo com o ciclo 2
  da metade A:** o cartão "Entregas por canal" em Conexões, uma linha por
  semana, WhatsApp / Telegram / (E-mail) / Falhas / **Telegram %** — a
  agregação por canal vem do campo `channel` da RPC, nunca do nome do
  provedor; `week_start` é `date` e não se desloca por fuso. **É o gate da
  sprint em forma de tela**: a coluna de WhatsApp caindo enquanto a de
  Telegram sobe. Sem gráfico nesta onda. Só `frontend/**`.

  **✅ Fechada em 17/09/2026 (`9151554`).** Vitest **914 → 953 / 50**, prettier,
  `tsc`, lint (os 3 warnings de sempre). `database.types.ts` regenerado
  contra o `operax_test` (porta 55322 nesta máquina): **+10 linhas**, só
  `fn_delivery_by_channel`. Premissas do implementador aceitas: `email` não
  está em `CHANNELS` (o `labels.test.ts` prende exatamente os dois canais)
  — o componente tem um mapa local só para o rótulo, e todo canal fora de
  `CHANNELS` vira coluna extra na ordem em que aparece, para a tabela sempre
  fechar com "Falhas"; a semana é formatada por split de string, e o teste
  troca `TZ` em runtime nos três fusos com um positivo ao lado; o cartão
  renderiza o `Card` inteiro, para a frase fixa existir nos três estados
  sem repetição. Falso verde respondido e medido: `meta_cloud` e `z_api` na
  mesma semana somando numa coluna só; provedor com `channel` invertido
  contando pelo canal declarado; `%` com e-mail presente usando só
  WhatsApp + Telegram no denominador; semana só de e-mail dá `—`.
  Revisão (ciclo 1, overlay): **APROVADA**, 40 mutações, 38 mortas; o único
  sobrevivente com peso era o `%` do rodapé — o teste dizia prender "razão
  das somas", mas na fixture a média dos `%` semanais também dava 35%
  (coincidência aritmética); fechei com a fixture 12/0 e 0/8, em que a razão
  é 40% e a média seria 50%, e provei no overlay que a mutação morre. Aceito
  como está: `channel: "sms"` (desconhecido) vira coluna com o código cru,
  como `label()` já faz — esconder faria "Falhas" não fechar. Dívida
  pequena: o rótulo "E-mail" mora no componente porque `email` não está em
  `CHANNELS`; vai para `labels.ts` quando ele for tocado.

**✅ Metade B fechada em 17/09/2026 (`a56732d`).** pytest **1066 → 1149** (83
novos em `tests/test_provedores_whatsapp.py`), ruff limpo; só os cinco
arquivos. `meta_cloud` manda `template.name` (`meta_template_name` vence o
`code`), `language` como veio e `parameters` na ordem de `variables` —
`render` não é sequer importado; `z_api`/`uazapi` mandam `render(body,
message)` byte a byte. Mapa de erro idêntico nos três, só código. `fabrica.
build` mapeia por módulo, sem literal de provedor, lendo cada campo do lado
que `FieldSpec.secret` declara. Premissas que ficam: a forma de resposta do
uazapi (`messageid → id → key.id`) e do Z-API (`messageId`, `zaapId` reserva)
nunca foram chamadas deste repositório; **a Meta responde token morto com
400, não 401** — pela tabela isso é `http_400`, e o sender não deve decidir
"descartar" por `unauthorized`; `cost_cents` é `None` nos três (a Meta cobra
por conversa e informa por webhook).
Revisão (ciclo 1, overlay): **APROVADA**, 61 mutações, as 20 do despacho
mortas; quatro sobreviventes de força de teste, fechadas por mim e provadas
mortas no overlay: `components` decidido por `variables` e não por `facts`
(o outbox manda sempre oito fatos — um template com zero variáveis viraria
`parameters: []`, o erro que a Graph API recusa); 2xx/3xx ≠ 200 recusado
(fail-closed, como o Telegram); `DecodingError` capturado (é `RequestError`,
não `TransportError`). 93 testes. Nota do revisor para quem puser outro
módulo não-provedor em `provedores/`: o `ast` do C1 permite literal em
`provedores/*.py` inteiro — a fábrica fecha a brecha com teste próprio, e o
próximo precisa do mesmo.

**Metade A entregue em 17/09/2026, em revisão + guardião.** pytest **1207**,
ruff, suíte de banco `SUÍTE COMPLETA OK` com **60** migrations (833 `ok`; `97`
sétima parte 64; `98` seção C5 21; `99` item 17). Duas migrations: `'telegram'`
no check da fila (**e uma cláusula em `util.validate_alert_template`** — o
gatilho é `before insert or update` e recusava `payload - 'link'`; agora o
update que leva a linha a `sent`/`discarded` não valida, e o `97` prova que
`failed`, `sending`, re-rota e insert continuam validando — fora da lista,
necessária, aceita por mim: não é policy, view de `public` nem grão de
`deviation_event`); `fn_delivery_by_channel` (invoker, `search_path = ''`,
sem `anon`, cinco colunas, lê só `alert_sent`) e `fn_telegram_adhesion` com
`order by`. `route` puro (identidade vigente **e** bot ativo); a chave de
idempotência **perdeu o destino** (quem aderisse entre duas execuções
ganharia duas mensagens) — produção medida em 17/09 com **zero** linhas em
`alert_queue`/`alert_sent`/`alert_rule`, nada colide. Sender em três fases,
gate aberto sem escrita, `sending` presa recuperada em 10 min com carimbo
na reserva, scrub em `sent`/`discarded`, `blocked` revoga e re-roteia na
mesma linha. `__main__.py` deixou de imprimir `destination` (era o `chat_id`
no stdout do Railway). **Limite conhecido, nomeado pelo implementador:** a
re-rota que o gatilho recusa (meta_cloud com template não aprovado) derruba a
fase (c) inteira. Três perguntas de desenho foram ao revisor com pedido de
medição: bot **ativo** vs. **pronto** no roteamento; último backoff de uma
linha Telegram cair para WhatsApp em vez de descartar; a degradação do
`blocked` em transação própria por linha.

**Guardião de superfície: PASSA**, 13 de 13, zero janelas sujas (21
conferências de hash). A RPC nova medida como papel, nas duas grafias de
claim: admin A vê só A, admin B só B, supervisor vê zero, `anon` recusado;
colunas exatamente as cinco; nenhuma view ou função de `public` alcança
`external_id`, `chat_id`, `alert_queue` ou `destination` (varredura com
controle positivo). O `chat_id` em claro fica só em `app.alert_queue.
destination`, que não sai por `public`. Segredos: uma leitura (`read_secret`),
um destino (`fabrica.build`), nenhum log. Observação aceita para o ciclo 2:
`_Batch` carrega `secrets` com `repr` padrão — `field(repr=False)` custa zero.

**Revisão (ciclo 1, overlay, `operax_rev_c5a`): APROVADA com um ALTO de
desenho.** 61 mutações, 55 mortas; os oito critérios medidos. O ALTO é o
"limite conhecido" com consequência maior do que a reportada: uma re-rota
recusada pelo gatilho (meta_cloud com template não aprovado) derruba a fase
(c) inteira, as linhas já entregues ficam `sending`, e **são reentregues a
cada retomada** enquanto a condição durar — medido com lote de 5. As três
perguntas de desenho, medidas: (D1) com token morto do bot, todo gestor
aderido perde toda mensagem por ~8 h por vez, sem cair para WhatsApp, e o
ciclo seguinte roteia por Telegram de novo; (D2) o último backoff de uma
linha Telegram descarta em vez de degradar, e `_REROUTE_SQL` soma `attempts`
(um `blocked` na 4ª re-roteia com 5 e a 1ª falha de WhatsApp descarta); (D3)
a degradação precisa de fronteira própria. Falso verde novo, medido: o chat
reatribuído — a ordem de `_IDENTITY_HOLDER_SQL` é load-bearing e nenhum teste
a segura (com a ordem invertida a mensagem de B iria para o WhatsApp de A).

**Ciclo 2 despachado em 17/09/2026, minhas decisões:** a degradação em dois
passos sem savepoint (c1 log+marcas de todas, commit; c2 um escopo por linha
a degradar, recusa → `discarded` com a frase do gatilho em outro escopo) —
`core/tenant.py` fica intocado; Telegram degrada por **três** causas —
`blocked` (revoga + re-roteia), erro de credencial do bot (re-roteia sem
revogar) e último backoff (re-roteia sem revogar) — e `_REROUTE_SQL` zera
`attempts` (a re-rota é só telegram → whatsapp, no máximo uma vez por linha);
o roteamento passa a exigir bot **pronto** (`active` **e** saúde `connected`,
o mesmo predicado de `fn_channel_readiness` — sem saúde, WhatsApp; o vigia
está agendado desde hoje); as oito sobreviventes fechadas; `repr=False` nos
segredos do lote. Registrado, não feito: `STUCK_MINUTES` é por requisição,
não por lote — vale enquanto há um sender só; o Sentry, quando for ligado,
precisa de `include_local_variables=False`.

**Ciclo 2 entregue em 17/09/2026, em re-revisão + re-gate.** pytest **1223**,
suíte de banco OK com **853** `ok` (`97` sétima parte 84), 14/14 mutações
mortas pelo implementador (inclusive o gatilho mutado no banco de ensaio).
A fase (c) virou dois passos: (c1) log e marca de todo o lote, com a linha a
degradar **estacionada** (`_PARK_SQL`: `failed`, tentativa contada, sem
`next_attempt_at`), commit; (c2) por linha, três escopos pequenos —
revogação + auditoria **antes** da re-rota, em escopo próprio (sobrevive à
recusa); a re-rota; e o descarte, que quando é recusa do gatilho deixa uma
**segunda linha em `alert_sent`** com `reroute_refused: <frase do gatilho>`
(a fila não tem coluna de erro; o log é o lugar durável). Telegram degrada
por três causas, só `blocked` revoga, `attempts = 0` na re-rota, uma vez por
linha. Roteamento por bot pronto: `join app.channel_health … status =
'connected'`, o predicado de `fn_channel_readiness`, provado no `97` com a
saúde mudando. O que ainda sairia duas vezes, nomeado e aceito: a janela
dos 10 minutos (processo morto entre o `enviar` e o (c1)) e uma exceção que
não seja `Delivery` no meio da fase (b) — ambos "retomada de `sending`
presa", o preço de não deixar a fila travada, válido enquanto há **um**
sender.

**Guardião, re-gate do ciclo 2: PASSA**, zero janelas sujas (25
conferências). A segunda linha de `alert_sent` da recusa foi provada por
três vias — o teste (o sender acrescenta só o prefixo), o `97` contra o
gatilho real (*"Template deviation_summary está draft e o provedor é
meta_cloud."*, sem link), e o **catálogo**: os dois gatilhos de
`alert_queue` foram enumerados linha a linha de `raise`/`format`, e nenhuma
mensagem interpola `destination` ou `payload` — só código de template,
nomes de variável e status. Revogação e auditoria em escopo próprio antes
da re-rota, provado pelo `FakeDB` transacional (`rolled_back == {4}` com a
revogação de pé). Uma lacuna de cobertura, não de comportamento: o teste
"identidade já revogada entre a fila e o envio" saiu no ciclo 2 sem
substituto; o guardião provou por sonda que a propriedade se mantém
(revoke 1, auditoria 0, re-rota 1). Restauro eu antes do commit.

**Revisão, ciclo 2: APROVADA.** O ALTO fechado e medido; 36 mutações, 33
mortas; três sobreviventes de força de teste, todos fechados por mim antes
do commit: a ordem dos escopos afirmada como **timeline** inteira (uma (c2)
aninhada dentro de (c1) daria a mesma contagem — e no banco real esperaria
para sempre pela linha que o `_PARK_SQL` deixou travada); um erro do banco
na re-rota provado a **propagar** em vez de virar descarte (o `except`
largo seria perda de mensagem silenciosa); o `str()` do stub do gatilho com
`HINT`/`CONTEXT`, para só `message_primary` satisfazer o teste; a asserção
do carimbo do `_PARK_SQL` com dois lados; saúde `unknown` e saúde
`connected` de **outra** integração provadas a não deixar o bot pronto, no
`97`; e o teste da identidade revogada entre a fila e o envio restaurado.
Registrado, não feito: `run()` não isola tenants (uma exceção pula os
seguintes naquela execução) — `try/except` por tenant quando o sender for
agendado; a segunda linha de `alert_sent` da recusa leva o hash do `chat_id`
rotulado `whatsapp` (opaco, nada vaza; semântica torta, documentada).
Portões finais: pytest **1225**, ruff, `SUÍTE COMPLETA OK` (60 migrations).

### ✅ C5 fechado no código em 17/09/2026

Três commits (`a56732d`, `9151554`, `524f786`), dois revisores em overlay
(quatro ciclos somados: 61 + 36 + 61 + 40 mutações), dois guardiões com zero
janelas sujas. Duas migrations novas: `20260917115527_ch_queue_telegram` e
`20260917115529_ch_delivery_by_channel` — **não estão em produção**.

**O que o C5 entrega quando o resto chegar:** um alerta de unidade sai pelo
Telegram de quem aderiu e pelo WhatsApp de quem não aderiu, a partir do
mesmo template; quem bloqueia o bot, ou cujo bot morre, volta para o
WhatsApp sozinho; a tela de Conexões mostra semana a semana a coluna de
WhatsApp caindo enquanto a de Telegram sobe — o argumento comercial da
etapa. **Nada disso sai hoje**: o sender e o outbox não estão agendados, e o
gate G4 segura tudo, inclusive o convite do C4 (decisão que continua com o
dono: abrir a exceção para o convite é uma cláusula na reserva).

**O que fica para o dono:** as **sete** migrations em produção (cinco do C3 +
duas do C5), na ordem captura → aplicar → captura → diff — e enquanto elas
não entram, o painel promovido não pode avançar; `FORWARDED_ALLOW_IPS=*`;
push de `524f786` (autorização própria); `vercel promote` depois das
migrations; agendar o sender depois do G4 — e nesse dia, `try/except` por
tenant no `run()`, e a janela dos 10 minutos passa a ser um risco com nome.

**O que a etapa Canais ainda não fechou** ("um alerta real chegando no
Telegram de um supervisor e o mesmo no WhatsApp de outro"): depende do G4,
das migrations em produção, da primeira credencial real e do primeiro
`/start` real — quatro coisas que só acontecem em produção, com o dono.
- **Decisão que fica com o dono, sem bloquear:** o convite do C4 sai pela
  mesma fila e o mesmo gate G4 — um convite não é alerta, e poderia sair
  antes do G4 (linha com `rule_id null` e `template_code = 'telegram_invite'`).
  O desenho desta onda mantém o gate para tudo, como o C4 registrou; abrir a
  exceção é uma cláusula no `_GATE_SQL`/reserva, se o dono quiser.

**Gate:** o relatório mostra a queda de volume no número de WhatsApp conforme a
adesão sobe. **É a métrica que justifica a etapa** — cada pessoa que sai do
WhatsApp é exposição a menos no número que a `DECISAO-WHATSAPP.md` §1 diz que
pode ser banido sem recurso.

---

## C6 — Destinatários e regras: a linha do S6 que nunca foi construída

**Por que existe:** o S6 previa "Tela de configuração de regras e destinos" e
entregou a esteira sem ela. Medido em produção em 21/09/2026: 27 unidades,
**0 contatos, 0 responsáveis por unidade, 0 regras, 0 destinos de regra, 0
templates**, nenhum canal ativo além do Secullum. A liberação do G4 abre uma
porta pela qual não passa nada — e "o que segurava a entrega era não existir
regra cadastrada" (migration 38) só é verdade porque não há como cadastrar.

**O que já existe e não muda:** as cinco tabelas (`app.contact`,
`app.unit_responsible`, `app.alert_rule`, `app.alert_rule_target`,
`app.message_template`) com policy `*_admin` (`util.is_admin`) e leitura por
`has_tenant`/`can_see_unit`; `util.validate_alert_target` (individual nunca
para grupo — regra 7, no banco); `util.validate_alert_template` (WhatsApp
oficial exige template do tenant); `active` nascendo `false`; a tela de
Conexões já nomeando regra bloqueada. **Nenhuma policy nova, nenhuma coluna
nova**: é aplicação sobre a fronteira que está lá.

**Onda 1 (backend):** rotas em `/canais/destinatarios` (contatos e
responsáveis por unidade) e `/canais/regras` (regra e destinos), padrão de
`canais.py` (`_require_admin` → leitura como o usuário → escrita + `audit_log`
sob `tenant_scope`). Regra nasce desligada; **ligar** exige ≥ 1 destino e, se
o canal inclui WhatsApp, `template_code` existente — o trigger é a rede, a
rota é o contrato com 409 nomeado. Nada de delete físico em contato ou regra
(`active = false`). Testes de rota com stub, `97_teste_canais.py` com o
cenário de ponta a ponta (contato → responsável → regra → destino → o outbox
enfileira → o sender, com o gate fechado, conta 1 esperando).

**Onda 1 entregue em 21/09/2026; revisada, corrigida e fechada no mesmo dia (abaixo).** `canais_regras.py`
(13 rotas, 27 instruções compiladas pelo `97`), modelos, `97_teste_canais.py`
com a oitava parte (contato → responsável → regra → destino → ligar → outbox
enfileira → sender com o gate fechado conta 1 e não grava). pytest 1500
(+91), suíte 67 migrations exit 0, sete mutações mortas. Decisões dele que
eu endosso e registro: `GET /regras` é do admin, porque `alert_rule_target`
só tem policy de admin e um supervisor receberia toda regra com `targets:
[]` e um "sem destino" **falso** (medido); desativar contato que é destino
direto de regra ligada é **409** listando as regras, porque `_TARGETS_SQL`
filtra `c.active` e a regra ficaria ligada entregando a ninguém em
silêncio; `ligar` exige também template **aprovado** quando o WhatsApp é o
oficial, porque a `RaiseException` do gatilho da fila sai de
`outbox.enqueue` matando o lote **inteiro** do tenant (pré-existente); o
chamador do `testar` é o contato pessoa com o e-mail do token — o único
fato de identidade que `auth.users` e `app.contact` carregam sem migration.

⚠️ **Dois achados que não são desta sprint:** (1) **`PUT` não estava em
`allow_methods` do CORS** — o preflight respondia 400, então
`PUT /canais/templates/{code}` (C1) e os `PUT` da configuração do assistente
(A3) **eram inalcançáveis pelo navegador em produção** com a suíte verde;
uma palavra em `main.py`, pinada por teste. **Corrigido em produção em
23/09/2026** (push `300aa46`): medido contra a API logo antes do deploy,
preflight `PUT` = 400 e `POST` = 200 — o defeito estava no ar; logo depois,
as **sete** rotas `PUT` respondem 200 ao preflight de
`https://app.fastparks.com.br` (as três pré-existentes e as quatro do C6),
origem de fora segue 400, `TRACE` segue 400, e as rotas novas pedem token
(401 sem ele). (2) **A regra 7 tem portas que o gatilho não vigia**:
`update content → individual` numa regra com grupo e `update type →
whatsapp_group` num contato destino de regra individual passam no banco
(medido); a API re-toca os destinos e faz o gatilho julgar. E a quarta porta
— o destino **por responsabilidade**, que o gatilho só reconhece como grupo
se `responsibility = 'group'` — fecha nos dois sentidos: grupo entrando na
matriz como `unit_manager` (422 em `PUT /unidades`) **e** pessoa que já é
`unit_manager` virando grupo (422 em `PUT /contatos`, o sentido que o
revisor mostrou aberto). A recomendação segue sendo uma migration futura
com `after update` fazendo o mesmo do lado do banco. Hoje nenhum produtor
emite conteúdo individual (`_TARGETS_SQL` filtra `aggregate`), então o furo
é latente.

**Guardião de superfície da onda 1 — APROVADO, 7/7, em 21/09/2026.** Suíte
inteira com o ensaio Deno (67 migrations, 434 `ok` no `97`, 98, 99, dicionário
sem diff, 39 documentos verificados); catálogo de banco idêntico antes e depois
(105 policies, 18 RPCs, 9 views, 94 colunas de view, 18 triggers — snapshot
por `diff`, não por leitura); API real com RLS real em dois tenants: 214
asserções, treze rotas com ids alheios → 404 e nunca 403, 24 × 403 de
supervisor e executivo **sem `tenant_scope` abrir** (contador de runtime) e
sem linha nova em `audit_log`; regra 7 pelas três portas (destino, regra,
contato) recusando 409 e o positivo entrando; trilha e log sem telefone (regex
sobre 10–15 dígitos fora de uuid, máscara `•••0611` aparecendo três vezes para
a varredura não ser vácua); dois cliques no `testar` = duas linhas com
`report_cycle_id` nulo, `deviation_event` intocado, e o sender contando 2 e não
gravando nada; preflight `PUT` do HEAD medido em overlay → 400 em sete rotas
(as três pré-existentes e as quatro desta sprint), na árvore → 200; o pino do
`97` contra delete físico **discrimina** (cópia mutada com `delete from
app.contact` cai). Árvore não editada: 16/16 hashes iguais em oito pontos.
Registros dele que ficam nomeados, sem reprovar: o supervisor de unidade lê o
WhatsApp de **todo** contato do tenant em `GET /contatos` (`contact_read =
has_tenant`, migration 04 — recortar é policy nova, parada obrigatória); o
e-mail do contato vai inteiro para a trilha (`audit_read = is_admin`, o mesmo
que lê `app.contact` em claro).

**Revisão independente da onda 1 — REPROVADA em 21/09/2026, e o que eu
consertei no mesmo dia.** O revisor rodou a API real contra o banco em oito
cenários, matou 20/20 mutantes em cópia e confirmou regra 4, `ligar` como
única porta, o modo de teste, a trilha, o CORS e o isolamento. Três gaps:

- **ALTO — a quarta porta da regra 7 só fechava num sentido.** Pessoa →
  `unit_manager` na matriz → `PUT /contatos type = whatsapp_group` chegava,
  só pela API e com três 2xx, a "regra `individual` ligada com um grupo
  resolvido por responsabilidade" — o estado que `PUT /unidades` recusa. O
  relatório da onda dizia "fechado" e não estava. Consertado: `update_contact`
  lê `_NON_GROUP_RESPONSIBILITY_SQL` dentro da transação e recusa 422
  `group_responsibility` (mesma frase) antes do `update`; teste pinando a
  ordem; o `97` mede as duas linhas do contato (Alfa `unit_manager`, Beta
  `hr`) e o zero do grupo só com `group`.
- **MÉDIO — regra ligada por responsabilidade ficava entregando a ninguém.**
  Desativar o único `unit_manager` ativo da unidade, ou tirá-lo da matriz
  pelo `PUT /unidades`, era 200 e silêncio — e pior: com uma **segunda**
  gestora ativa, o outbox escolhia a primária (`order by is_primary desc
  limit 1`) **antes** de filtrar `c.active`, e a regra entregava a ninguém
  mesmo assim. Consertado nos dois lados: (a) `desativar` e `PUT /unidades`
  perguntam `_LAST_RESPONSIBLE_RULES_SQL` — as regras ligadas cujo destino
  por responsabilidade deixaria de resolver em alguma unidade, descontado o
  que a matriz nova mantém (`kept`) e contando só contato ATIVO — e recusam
  409 `contact_last_responsible` listando as regras, na mesma transação;
  (b) `outbox._TARGETS_SQL` filtra `rc.active` **dentro** da subconsulta,
  antes do `limit 1`: a primária inativa cai para a próxima ativa. É a única
  linha fora de `canais_regras.py`, e é a raiz — sem ela a cerca da API
  teria de espelhar um defeito. O `97` mede o fallback (a segunda gestora
  alcançada com a primária inativa) e o `0` quando não sobra ninguém.
- **MÉDIO, pré-existente (C3/C5), não desta sprint:** `ciclo.assemble`
  commita a reserva dos desvios e `outbox.enqueue`, noutra transação,
  levanta no primeiro alvo doente — o lote inteiro do tenant volta, e os
  desvios ficam reservados num ciclo `open` sem mensagem (`report_cycle_id
  is null` é a cláusula da reserva; eles **não voltam**). O `ligar` desta
  sprint só mitiga ao ligar. Fica nomeado para sprint própria: pular a regra
  doente com log e `blocked_reason`, ou reservar e enfileirar na mesma
  transação.

Sete mutantes meus, mortos na minha cópia (nunca na árvore): a cerca de
`update_contact` (mA), a de `desativar` (mB), a de `PUT /unidades` (mC), o
outbox do HEAD (mD — o pytest pina o texto e o `97` devolve nulo em vez da
segunda gestora), `me.active` fora da consulta (mE — o `97` acusa 1 onde é 0,
só com a segunda desativada também: com ela ativa o "outro titular" já zera e
o mutante sobrevivia, e foi por isso que a seção 13 ganhou esse estado),
`c.active` do outro titular (mF) e o `kept` ignorado (mG). BAIXOs do revisor
consertados por serem texto: o comentário do `_TEST_FACTS_SQL` (não é
"`_RESERVE_SQL` sem o `update`": não filtra `report_cycle_id is null`, de
propósito) e o rótulo da seção 9 do `97` (as duas instruções do gate são
leituras; o "não grava" do ramo Python está em `test_alertas_sender.py`).
BAIXOs registrados sem mexer: `silenciar` audita com `antes = null`;
`testar` identifica o chamador só pelo claim `email` (o Supabase o liga ao
`sub` na emissão; não há o que cruzar sem migration) e não tem rate limit
(admin-only, gate fechado); `_BLOCKED_SQL` casa por `rule_name`, não único
(equivale por template; `rule_id` na lista é dívida do `canais.py`); race
pequena entre `ligar`/`desativar` concorrentes (instância única). Pergunta
de produto para o dono, que os dois gates levantaram: **o supervisor de
unidade lê o WhatsApp e o e-mail de todo contato do tenant** em
`GET /contatos` (`contact_read = has_tenant`, migration 04) enquanto a trilha
mascara o número — recortar é policy nova, parada obrigatória. Gates depois
das correções: pytest 1505 (+5), ruff limpo, `97` com 444 `ok` (seção 13
nova), suíte de banco 67 migrations exit 0.

**Onda 2 (frontend):** aba **Destinatários** (contatos e a matriz
unidade × responsabilidade) e aba **Regras** em `/dashboard/administracao/`,
porta `isAdmin`, e o modo de teste do S6: *"rodar primeiro com destino no
próprio owner"* como um botão, não como uma instrução. **Despachada em
21/09/2026** sobre `0820662` — a onda 1 (`378eefa`) mais
`GET /canais/regras/tipos-de-desvio`, porque `app.deviation_type` não chega
ao navegador e a tela precisa do rótulo (uma leitura global como o usuário;
a policy é `true`).

**Onda 2 entregue em 23/09/2026, em revisão.** Duas páginas
(`destinatarios/`, `regras/`) com porta `isAdmin` (404, não tela vazia),
`components/canais/contacts.tsx` e `rules.tsx`, o cliente
`lib/canais/regras.ts` com os tipos espelhando `models.py` campo a campo e
as onze mutações, três leituras de servidor em `queries.ts`, e os dois
`NavLink` dentro de `showAdminWrites`. Vitest 1169 (+83), tsc e prettier
limpos, build exit 0, oito mutações mortas em cópia. Decisões dele que eu
endosso: tipos de desvio pela API (`app.deviation_type` não está exposto e
expor view nova é parada obrigatória), unidades por `vw_unit` com o
`loadUnits` que já existe (uma segunda leitura seria definição concorrente),
e `blocked_reason` renderizado **como veio** — o backend o calcula de três
leituras, e uma segunda implementação no navegador divergiria em silêncio.
Uma mudança fora de `canais/`: `ApiError` passou a carregar `code` e
`payload` (com `readDetail` delegando ao novo `readRefusal`), porque sem
isso a tela não ramifica em `caller_has_no_contact` nem lista as regras de
um 409 — era a dívida já anotada em `telegram-link.tsx`.

⚠️ **O falso verde desta tela, nomeado pelo implementador e que eu registro
como do produto, não do código:** `blocked_reason` nulo numa regra ligada
significa "as três leituras do backend não têm o que apontar", **não** "vai
entregar". Ficam de fora dele o gate G4 (hoje fechado: a regra ligada
entrega zero), a saúde do provedor na hora do envio, `content = 'individual'`
(que nenhum produtor emite — `_TARGETS_SQL` filtra `aggregate`) e o destino
por responsabilidade que não resolve. A tela não traduz nulo para nada:
a insígnia diz só "Ligada", e uma linha fixa nomeia a diferença.

**Revisão independente da onda 2 — APROVADA em 23/09/2026, com três MÉDIOs
que eu consertei antes do commit.** Ele mediu os treze critérios com render
de verdade: contrato campo a campo (14 modelos, mesma ordem, nenhum campo
opcional), `isAdmin` da tela = `util.is_admin` da rota, regra 7 medida na
lista de destinos, as sete recusas nomeadas virando a frase do backend, PII
sem ir para log, URL ou storage, e onze mutantes em cópia — oito mortos,
**três sobreviventes**, que viraram os achados:

- **O "sinal a mais" era cego para a unidade.** A tela contava "existe
  alguém ativo com esta responsabilidade em alguma unidade", mas o
  `outbox._TARGETS_SQL` resolve **por unidade do ciclo**. Cenário medido por
  ele: duas unidades, um gestor ativo só na Alfa, regra de **todas** as
  unidades — a tela calava e a Beta entregava a ninguém (em produção seriam
  26 de 27), e "todas" é o default do formulário. Consertado: `coverage()`
  conta por unidade e a tela diz "resolve em 1 de 27 unidades"; teste com
  duas unidades e um resolvedor só.
- **Nada prendia que o eixo da ramificação é o `code`.** Trocar
  `refusalCode(...) === "caller_has_no_contact"` por um `includes` da frase
  passava na suíte inteira, porque o `detail` do fixture citava
  "Destinatários" — e o link sumiria no dia em que o backend reescrevesse a
  frase. Consertado com um teste nos dois sentidos: código certo com frase
  que não cita, e outro código com frase que cita.
- **O `detail` não-string não estava pinado.** O 422 de validação do FastAPI
  manda `detail` como lista; transformá-la em JSON despejaria isso na tela
  sem teste vermelho. Pinado.

Dois BAIXOs dele que também consertei por serem texto errado: a frase do
destino descartado afirmava "por estar desativado" em caso que não é
desativação, e **silêncio vencido continuava como insígnia de silêncio** —
o outbox já entrega quando `muted_until <= now()`. O relógio passou a ser
lido no servidor (ler a hora no render do cliente é chamada impura, e o
lint do React barra), como a página de Colaboradores já faz. Quatro
mutantes meus na cópia, quatro mortos. Gates depois das correções: vitest
**1173** (+4), tsc, prettier e build limpos, lint com os 3 warnings
pré-existentes.

⚠️ **Uma pergunta para o dono, que o revisor levantou e eu não consertei
porque é do modelo, não da tela:** uma regra `individual` pode ter uma
**lista de e-mail** como destino. A tela oferece, e o banco aceita — o
gatilho `util.validate_alert_target` só conhece `whatsapp_group` e
`responsibility = 'group'`. Mas a regra 7 do `CLAUDE.md` diz "alerta de
conteúdo individual nunca vai para grupo", e `dp@cliente.com.br` é uma
caixa que várias pessoas leem. Fechar isso é migration + rota no mesmo PR,
e muda o que o produto permite — por isso está aqui e não no código.

**Em produção desde 23/09/2026.** Push `e16e85d` (o Railway reconstruiu o
`operax-api` sozinho) e `vercel promote` do `dpl_Bu9JagxHYB1rJWxTNxcPyGzkgBAd`,
que reconstrói com o ambiente de produção. Conferido contra
`app.fastparks.com.br`: `/dashboard/administracao/destinatarios` e
`/regras` respondem 307 para `/login?next=…`, igual à tela de Conexões que
já existia — as rotas existem e a sessão é exigida antes delas.

**Sem guardião de superfície nesta onda, por julgamento meu:** ela não toca
`supabase/**`, `deps.py`, `core/**` nem cria objeto em `public`, e não abre
superfície de escrita de PII — as leituras passam por rotas que o guardião
da onda 1 já mediu, e a página é fechada por `isAdmin`. O que ela **mostra**
de PII (WhatsApp e e-mail em claro) é o item 9 do despacho da revisão.

**Gate:** com o G4 fechado, cadastrar uma regra ligada com um destino faz o
sender contar "1 esperando" no próximo turno — sem entregar. Com o G4 aberto,
um alerta real chega ao destino de teste (o owner) e é o que fecha a etapa
Canais.

## C7 — O ciclo reservado sem mensagem: a perda silenciosa que espera o G4

✅ **Fechada em 23/09/2026** (`d2753cf`). O que segue descreve o defeito
**como ele era** — o texto no presente é a fotografia de antes, não o estado
de hoje; a `TemplateMismatchError` que ele cita deixou de existir.

**Por que existia:** `ciclo.assemble` e `outbox.enqueue` rodavam em
**transações separadas**. `assemble` commitava a reserva (`report_cycle_id`
preenchido); `enqueue`, depois, levantava `TemplateMismatchError` no primeiro
alvo doente e **o lote inteiro do tenant voltava** — os desvios ficavam
reservados num ciclo sem nenhuma mensagem, e `_RESERVE_SQL` exige
`report_cycle_id is null`, então eles **nunca mais entravam em ciclo nenhum**.
Nomeado pelo revisor do C6 nas duas ondas; **reproduzido por mim contra o
banco em 23/09/2026**, com uma regra de WhatsApp apontando para template
inexistente e uma de e-mail saudável ao lado:

```
antes de tudo:       ciclos 0 · reservados 0 · livres 2 · fila 0
depois do assemble:  ciclos 1 · reservados 2 · livres 0 · fila 0
enqueue levantou TemplateMismatchError: regra 'Doente…' aponta para o template 'nao_existe'
depois do enqueue:   ciclos 1 · reservados 2 · livres 0 · fila 0   ← a regra de e-mail perdeu a dela
segundo turno:       assemble devolveu 0 ciclo(s)
  preso: late_entry em ciclo open com total_events=2 e ZERO mensagem
  preso: late_exit  em ciclo open com total_events=2 e ZERO mensagem
```

**Por que não tinha doído ainda, e por que doeria:** com o G4 fechado nada é
entregue mesmo, e em produção há zero regras. O `ligar` do C6 exige template
presente, ativo e aprovado — então a regra só adoece **depois** de ligada
(template desativado ou reprovado na Meta em seguida), que é exatamente o
caso que o C6 já mede em `blocked_reason`. No dia em que o gate abrir, um
template desativado à tarde apaga em silêncio os indícios daquele dia, para
todas as regras daquele cliente, para sempre.

**O que fazer:**
1. **Uma transação só.** É a intenção declarada no próprio
   `backend/operax/alertas/__main__.py`: *"um ciclo montado e não enfileirado
   é o pior estado possível"*. Montar e enfileirar têm de commitar juntos.
2. **A regra doente é pulada e nomeada, não fatal.** Uma regra que não
   consegue montar a mensagem não pode calar as outras do mesmo cliente. O
   relatório diz qual foi e por quê.
3. **Ciclo que terminou sem mensagem nenhuma é desfeito.** O FK é
   `on delete set null`, então apagar o ciclo devolve os desvios ao próximo
   turno sozinho — é o que `_DROP_EMPTY_SQL` já faz para o ciclo vazio, agora
   também para o ciclo mudo. É o que torna o conserto auto-curável: template
   arrumado, o turno seguinte entrega.

⚠️ **Resíduo que eu declaro, e não escondo:** o ciclo é por **unidade**, e as
regras também cobrem unidades. Se uma regra saudável e uma doente cobrem a
mesma unidade, a saudável entrega e os desvios são consumidos — a audiência
da regra doente perde aquela janela. A alternativa seria segurar todo mundo
até alguém consertar o template, o que troca uma perda por um atraso. Fico
com entregar a quem dá, consumir, e dizer alto qual regra ficou de fora;
`blocked_reason` já mostra a regra travada na tela de Regras.

**Não muda:** o grão de `app.deviation_event`, nenhuma policy, nenhuma coluna
nova, nenhuma migration. Desvio continua sem nunca ser apagado (regra 6) — o
que se apaga é o ciclo mudo, e o FK devolve o desvio.

**Gate:** o cenário acima, virado. Com a regra doente: a de e-mail entrega, o
relatório nomeia a doente, e — quando a doente é a única — o ciclo não existe
e os desvios continuam livres para o turno seguinte.

**Guardião de superfície da C7 — APROVADO, 7/7, em 23/09/2026.** Chamado por
julgamento meu e não pela lista automática, porque a sprint cria um DELETE
novo em `app.report_cycle` e `alert_queue_report_cycle_id_fkey` é
`on delete cascade`. Ele começou provando que o perigo é real — apagando um
ciclo **sem** a guarda, e a mensagem sumiu junto (`fila antes 1 → depois 0`)
— e só então mediu os seis casos com dois tenants: ciclo mudo some e os
desvios voltam; ciclo com mensagem `pending` e com `sent` ficam de pé; um
ciclo antigo com mensagem **na mesma unidade** sobrevive ao DELETE do mudo;
o tenant B não perde nada. Em todos, `deviation_event` global constante
(regra 6). Mais: catálogo idêntico antes e depois (389 linhas, mesmo sha256),
as 10 instruções dos dois módulos ligando o tenant e recusando o id do
vizinho nas quatro escritas, PII ausente do relatório e do log com a
varredura provada não-vácua, quatro mutantes dele mortos em cópia (inclusive
o `not exists` removido), e o sender seguindo inerte com o gate fechado.

Três observações dele, que eu registro:
- **O1 — `make db-test` não arma o teste novo.** O passo do `85` é opt-in em
  `ENSAIO_DATABASE_URL` e o ramo sem a variável **não falha**; o `Makefile`
  chama o script sem ela. Ou seja: um `make db-test` verde não prova a
  garantia da C7. É a mesma convenção do ensaio Deno (que já era assim), mas
  aqui o que fica sem medir é a fronteira da transação. **Vou consertar.**
- **O2 — o comentário promete mais do que o predicado entrega.** O
  `not exists` foi descrito como proteção contra o `on conflict do nothing`;
  na prática um ciclo recém-criado nunca tem linha antiga apontando para ele,
  e o que o predicado de fato garante é o recorte **por ciclo** (um critério
  sobre a lista achatada do lote teria derrubado o ciclo com mensagem junto).
  O resíduo do caso de conflito é transitório e se cura sozinho — medido.
  **Vou corrigir o comentário.**
- **O3 — o `85` é o primeiro script de `scripts/` que commita e depois
  apaga.** Os outros rodam dentro de `rollback;`; este não pode, porque o que
  ele testa é a fronteira da transação. Alcance medido e correto (toda
  cláusula por `tenant_id` próprio), mas fica nomeado: apontado para um banco
  não descartável, o `delete` não tem rede.

**Revisão independente da C7 — REPROVADA em 23/09/2026, e os consertos que
eu fiz antes do commit.** Ele confirmou que o conserto aguenta — atacou o
predicado por sete lados — e reprovou pela régua: **seis das oito mutações
dele sobreviviam à suíte**, entre elas apagar o filtro de tenant de um
`delete` que tem `on delete cascade` atrás. Três gaps ALTOS:

- **O critério 2 da própria sprint não se cumpria no caso que ela nomeia.**
  `_template_reason` cobria dois dos três motivos de
  `util.validate_alert_template`; faltava `meta_status <> 'approved'` no
  provedor oficial — o "reprovado na Meta depois de ligada" que o texto da
  C7 cita com todas as letras. Medido: a regra doente calava a saudável.
  Consertado perguntando os **três** motivos antes do insert, com uma
  consulta própria (`_TEMPLATE_FOR_CYCLE_SQL`) para não mexer no
  `_TEMPLATE_SQL` que três rotas leem. Quem decide se o provedor exige
  template aprovado é a **matriz de capacidades**, nunca o nome escrito no
  código — há um teste no projeto que proíbe a literal, e ele me pegou.
- **Um tenant doente derrubava o turno de todos os outros.** O laço de
  `_montar_e_enfileirar` não tinha `try` por tenant — a mesma dívida que o
  `run()` do sender fechou em `a8f589c`, na função que esta sprint
  reescreveu. Consertado na mesma forma, com o tenant que falhou nomeado no
  relatório. É também a contenção estrutural do que o Python **não** pode
  prever: gatilho novo, constraint nova, banco caindo no meio.
- **O `delete` mais perigoso da sprint estava sem teste nos dois eixos que
  importam.** Os cinco cenários eram um tenant, uma unidade, e a fila
  esvaziada à mão — e em produção a fila nunca está vazia, porque o sender
  só faz `update`. O `85` ganhou quatro cenários: duas unidades no mesmo
  turno (só a muda cai), fila cheia, segundo tenant, e o filtro de tenant
  exercitado de frente (entregando ao `drop_silent` o id do ciclo do
  vizinho). O cenário 5 deixou de recopiar o predicado à mão e passou a
  chamar `ciclo.drop_silent` — era o falso verde contra o qual o próprio
  arquivo argumenta.

Os MÉDIOs e BAIXOs também fechados: a guarda do `not exists` era **mais
estreita** que o cascade que ela protege (filtrava `q.tenant_id`, e a FK não
amarra tenant — uma linha de fila alheia apontando para o ciclo era aceita
pelo banco e invisível à guarda); a regra sem destino no canal sumia sem
culpado (agora é `Skipped` nomeado); o aviso repetia por destino e por ciclo
(agora um por regra); o relatório contava ciclos que ele mesmo desfazia. E
as duas do guardião: o comentário que prometia mais do que o predicado
entrega, e o **`make db-test` que não armava o teste novo** — o passo era
opt-in e o ramo sem a variável passava verde. Agora ele **falha alto**, e
ainda recusa um DSN que não seja o do banco recém-migrado; o `Makefile`
passa o DSN. Sete mutantes meus, sete mortos em cópia, incluindo os quatro
que sobreviveram ao revisor.

⚠️ **O cenário 4 teve de mudar de causa, e isso é consequência boa:** ele
usava `meta_cloud` + template em rascunho para forçar a recusa do banco, e
esse motivo agora é **pulado** em vez de estourar. A prova da transação
única passou a usar um gatilho de teste que o código não conhece — a classe
"recusa imprevista", que é o que sempre vai sobrar e o que o `try` por
tenant contém. Prender o cenário a um motivo específico o faria apodrecer no
dia em que alguém o passasse a prever.

⚠️ **E um achado que não é da sprint, medido em 23/09/2026 enquanto eu
conferia o entrypoint: NINGUÉM monta o ciclo em produção.** O projeto do
Railway tem cinco serviços — `operax-api`, `operax-motor`
(`python -m operax.motor`, `*/15`), `operax-motor-retro`, `operax-vigia` e
`operax-sender` (`python -m operax.alertas.sender`, `*/15`). **Nenhum roda
`python -m operax.alertas`**, que é quem monta o ciclo e enfileira. Ou seja:
o motor detecta, o sender consome, e no meio não há quem encha a fila. O
"0 mensagem(ns) esperando" que o sender loga desde 21/09 não é só o gate
fechado — é também a fila vazia por falta de produtor. **No dia em que o G4
abrir, nada seria entregue mesmo com regra cadastrada e credencial ativa.**
Agendar esse serviço é o passo seguinte, e é justamente a C7 que o torna
seguro: hoje um template desativado deixaria rastro permanente a cada
quinze minutos.

## Ordem

```
C0 ── C1 ── C2 ── C2b ──┬── C3 ── C4 ── C5
                        │
                        └─ (C1+C2+C2b já entregam sozinhos)
```

## O que fecha a etapa

Um alerta real chegando no Telegram de um supervisor **e** o mesmo alerta
chegando no WhatsApp de outro, com o mesmo texto, a partir de um template só — e
a tela de Conexões mostrando os dois canais saudáveis, com data.

## O G4 em 21/09/2026 — o que ele exige, e o que foi feito

Decisão do dono em 21/09: fechar o G4 e agendar o sender. Medido antes de
tocar em qualquer coisa: o motor roda em **modo produção desde 09/09** (2.118
execuções completas), emitindo ~170 indícios por dia útil — 4.649 ativos, zero
julgados; o censo de sombra dos 820 (29/08–04/09) é população anterior, também
com zero julgados. A liberação é uma linha em `app.alert_release` que o schema
**só aceita com censo completo e taxa ≤ 5%** (migration 38, autorizada pelo dono
em 11/09 justamente porque o motor tinha sido promovido com o censo em zero).
"Declarar no piso" não existe no sistema; afrouxar o check seria desfazer a
decisão de 11/09. O que existe é o censo por janela.

Feito em 21/09:
- **Censo exportado**: `~/operax-censo/censo-g4-producao-17a18set.xlsx`, 352
  indícios de 17 e 18/09 (dois dias úteis fechados; o dono pediu ~300), com o
  `LEIA-ME.md` ao lado dizendo o que preencher. Fora do repositório — é PII.
  O CLI ganhou `--ate` para o censo não incluir o dia em andamento (3 dias
  terminando numa segunda davam 36 indícios: sábado, domingo e a manhã).
- **`run()` do sender isolado por tenant** (`a8f589c`): a dívida nomeada no
  fechamento do C5. Um cofre fora do ar num tenant não silencia mais a fila
  dos outros; o que falhou aparece pelo nome no relatório.
- **`operax-sender` no Railway** (`f7a91382-…`), `python -m operax.alertas.sender`,
  `*/15 * * * *`, restart NEVER, variáveis por referência ao `operax-api`, mesma
  receita do vigia. Com o gate fechado ele só conta o que espera e não grava
  nada — é seguro estar no ar antes da liberação, e é a prova de que a porta
  está fechada de verdade.
- `OPENAI_API_KEY` conferida no `operax-api` por `describe-service` (nomes,
  nunca valores). `FORWARDED_ALLOW_IPS` não está lá; segue como recomendação.

O que falta, e é de gente: alguém julga as 352 linhas; depois `importar`,
`medir`, `liberar`. Aí o sender entrega — para as regras cadastradas (hoje
**zero** em `app.alert_rule`) e pelos canais com credencial ativa (hoje nenhum
bot de Telegram ativo, e a primeira credencial de WhatsApp ainda é a parada
adiada do C2). A liberação abre a porta; regra e credencial são o que passa
por ela.

## O que fica fora

- **QR na tela** — conectar `z_api`/`uazapi` continua sendo no painel deles.
- **Reconexão automática** (SPEC §7).
- **Bot conversacional** — o webhook trata `/start` e nada mais.
- **Botão e teclado do Telegram** — entram quando forem declarados no template.
- **Grupo no Telegram** — precisa de `type = 'telegram_group'` em `app.contact`
  e de `util.validate_alert_target` cobrindo o valor novo, ou a **regra 7 fica
  cega no canal novo**. Fora daqui, e quando entrar, entra com a regra junto.

## Uma linha que é da etapa DP, não desta

`birthday_greeting` e `cnh_renewal_request` (S4 do DP) são endereçados ao
**colaborador**, e colaborador não está em `app.contact`. Esta etapa resolve o
destino de Telegram; a rota de **WhatsApp para colaborador** continua sem modelo.
**Vale registrar em `SPRINTS-DP.md` antes do S4 começar.**
