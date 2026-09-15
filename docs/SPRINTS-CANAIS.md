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

### ⏳ C2, metade de frontend — despachada em 14/09/2026, em paralelo com o ciclo 2 do backend

O contrato (`ProviderForm`, `FieldForm`, `CredentialStatus`, `CredentialRequest`)
está fixado em `models.py` e o ciclo de correção do backend não muda a forma —
por isso as duas metades correm juntas, em arquivos disjuntos. **§5.4 é o gate
desta metade:** o formulário é dirigido pelos dados de `GET /canais/provedores`
(`autocomplete`, `inputmode`, `pattern`, `secret`, `hint` vêm da API), a
validação Zod usa o mesmo `pattern` que o backend impõe, e o segredo nunca
volta — campos secretos limpos após sucesso.

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

- as **oito** linhas da SPEC §2.2 viram `tests/db/test_channel_exclusivity.sql`,
  e a linha 1 (os dois canais coexistindo) é a que não pode passar por revisão de
  código — só o índice real responde;
- o mesmo alerta sai por WhatsApp e por Telegram com **texto idêntico**, a partir
  de um template só;
- `/start` com token inválido, expirado ou já usado **não vincula**, e as três
  recusas são distinguíveis no log;
- requisição no webhook sem o header secreto é descartada **antes** do parse;
- derrubar o bot e rodar o vigia muda o status e **não** tenta reconectar.

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

## C5 — Roteamento e medição

- `Telegram se houver identidade vigente; WhatsApp caso contrário.`
- Entrega por canal em `app.alert_sent`.

**Gate:** o relatório mostra a queda de volume no número de WhatsApp conforme a
adesão sobe. **É a métrica que justifica a etapa** — cada pessoa que sai do
WhatsApp é exposição a menos no número que a `DECISAO-WHATSAPP.md` §1 diz que
pode ser banido sem recurso.

---

## Ordem

```
C0 ── C1 ── C2 ──┬── C3 ── C4 ── C5
                 │
                 └─ (C1+C2 já entregam sozinhos)
```

## O que fecha a etapa

Um alerta real chegando no Telegram de um supervisor **e** o mesmo alerta
chegando no WhatsApp de outro, com o mesmo texto, a partir de um template só — e
a tela de Conexões mostrando os dois canais saudáveis, com data.

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
