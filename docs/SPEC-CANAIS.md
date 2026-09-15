
# OperaX — SPEC de canais: tela de Conexões e entrada do Telegram

Duas coisas, na mesma etapa porque a segunda não faz sentido sem a primeira:

1. **A tela de Conexões** — o OperaX tem três provedores de WhatsApp, catálogo
   de templates, prontidão calculada e **nenhuma tela**. Hoje ninguém enxerga
   por que um alerta não sai.
2. **O Telegram como quarto provedor** — decisão do owner em 05/09/2026,
   alcançando **responsáveis e colaboradores**.

---

## ⚠️ Procedência — a mesma advertência das duas SPECs anteriores

Escrita contra o **snapshot de 15 migrations** deste diretório; o repo em
andamento tem **37**. Toda linha da §0 precisa ser reconferida antes de virar
premissa. A reconferência está no A0 de `SPRINTS-CANAIS.md`.

## ⚠️ Correção que esta etapa obrigou a fazer

`SPEC-AGENTE.md` §6.1 afirmava que a regra 11 *"existe para que nenhum texto
livre chegue ao WhatsApp de uma pessoa"*. **Errado.** O `CLAUDE.md` diz:
*"Provedor de WhatsApp recebe `(template, variáveis, destino)` — nunca string
pronta. (…) texto livre exclui o oficial de forma irreversível."*

A regra é de **interoperabilidade**, não de privacidade. As de privacidade são a
**7** (conteúdo individual nunca vai para grupo) e a **10** (saúde sem
diagnóstico). Os dois documentos já foram corrigidos; está registrado aqui
porque a distinção decide o desenho do Telegram inteiro — ver §2.

---

## §0. O que o OperaX tem hoje

| Objeto | Estado |
|---|---|
| `app.integration` | `provider` com 8 valores; `unique (tenant_id, provider, alias)` |
| `integration_whatsapp_unico_ativo` | índice parcial: **um** provedor de WhatsApp ativo por tenant |
| `app.integration_secret` | **só o ponteiro** — `vault_id` → `vault.secrets`. *"Nenhum role do painel lê esta tabela — nem owner."* |
| `app.message_template` | por tenant; `variables`, `body` (render local), `meta_template_name`, `meta_status` |
| `util.validate_template_body()` | corpo usa exatamente os placeholders declarados |
| `util.validate_alert_template()` | payload cobre as variáveis; `meta_cloud` só aceita `approved` |
| `public.fn_whatsapp_readiness()` | `ready`, `templates_approved`, `rules_blocked` |
| `app.contact` | destinatário: `whatsapp`, `email`, `type in ('person','whatsapp_group','email_list')` |
| **Tela** | **não existe** |

**Consequência de hoje, verdadeira e cara:** `fn_whatsapp_readiness` já sabe
dizer que o tenant está bloqueado e por quê — *"nesse estado o alerta falha
calado"*. Ninguém lê. Diagnóstico existente e invisível é diagnóstico que não
existe.

### 0.1 O destinatário de hoje é o responsável, não o colaborador

`app.contact` alimenta `app.unit_responsible` com papéis
`unit_manager · regional_supervisor · personnel · hr · executive · group`. São
**dezenas de pessoas**.

Os templates que a etapa DP criou — `birthday_greeting`, `cnh_renewal_request` —
são endereçados ao **colaborador**, e colaborador **não está em `app.contact`**.

⚠️ **Achado lateral, e é da etapa DP, não desta:** os dois templates do S4 não
têm modelo de destinatário. A §3 resolve para o Telegram; a rota de WhatsApp
para colaborador continua sem destino modelado. **Vale uma linha em
`SPRINTS-DP.md` antes do S4 começar** — não é escopo daqui.

---

## §1. A doutrina que vale a pena importar (e não é uma tela)

O item mais valioso do DeskcommCRM nesta área não é nenhuma das seis telas. É
`lib/channels/capabilities.ts`, e o cabeçalho dele:

> *"O ÚNICO lugar do sistema que pode conhecer a diferença entre os canais.
> Feature nenhuma pergunta **com quem** falamos — pergunta **o que o canal
> permite**. Capability que ninguém consome é código morto, e o teste de matriz
> reprova."*

Com resolução **fail-closed**: provedor desconhecido **lança**, não cai num
default. E o default declarado é o canal **conservador** — *"errar para o lado
do `meta_cloud` desarmaria o anti-ban num número que pode ser banido"*.

Isso é exatamente o que falta no OperaX: hoje a diferença entre `meta_cloud` e
os não oficiais está espalhada em `util.validate_alert_template`, no comentário
de `app.integration.provider` e na cabeça de quem leu a `DECISAO-WHATSAPP.md`.
Com um quarto canal entrando, espalhar mais é como o contrato se perde.

### 1.1 O Telegram é uma **terceira família de restrição** — e isso é o achado

O DeskcommCRM separa os canais em duas famílias e tem um teste que afirma que
elas **nunca coexistem**:

- **auto-restrição** (`banRisk: true`) — *"falo quando quiser, mas o WhatsApp me
  bane se eu abusar"* → `z_api`, `uazapi`;
- **hetero-restrição** (`requiresTemplates: true`) — *"não me banem, mas a Meta
  me proíbe e me cobra"* → `meta_cloud`.

**O Telegram não tem nenhuma das duas.** Sem janela de 24h, sem template
aprovado, sem risco de banimento por volume, sem custo por mensagem. Pelo teste
deles, passa — ter *nenhuma* não é ter *as duas*. Mas quebra a premissa
implícita de que todo canal é restrito de **alguma** forma, e a leitura ingênua
disso é *"o Telegram é o canal sem regra"*, que é falsa e perigosa.

A restrição do Telegram existe e é de outro eixo:

> **Restrição de destinatário.** O Telegram **não envia para um número de
> telefone.** Ele envia para um `chat_id`, que só passa a existir quando a
> pessoa inicia conversa com o bot. WhatsApp restringe **o que** você diz e
> **quando**; Telegram restringe **para quem**.

Capability nova, e ela é o que a §3 inteira existe para atender:

```ts
requiresRecipientOptIn: true   // telegram
```

⛔ Nenhum arquivo fora do módulo de capabilities escreve `'telegram'`,
`'meta_cloud'`, `'z_api'` ou `'uazapi'` como string literal. É o que o
`lint-channels` deles cobra, e é o que impede o quarto canal de vazar em `if`
espalhado.

---

## §2. Telegram entra **sob o contrato de template** — não ao lado dele

O Telegram aceita texto livre. A tentação é óbvia: *"ele não precisa de
template, por que passar por um?"*

Não passa. E o motivo não é a regra 11 mal citada da versão anterior — é este:

1. **`app.message_template.body` já existe para render local.** É o caminho que
   `z_api` e `uazapi` usam hoje. O Telegram usa o mesmo, sem uma linha de
   arquitetura nova. O custo de obedecer ao contrato é **zero**.
2. **Um remetente de texto livre no código é o objeto perigoso**, não o canal
   que o justificou. Depois que ele existe, ligar a saída do assistente nele é
   uma linha — e é exatamente o que a `SPEC-AGENTE.md` §6.1 diz para não
   construir. A regra 11 protege o provedor oficial; **este parágrafo protege a
   fronteira assistente → sender**, que é argumento independente e sobrevive a
   qualquer mudança na regra 11.
3. **`util.validate_alert_template` já garante que payload e variáveis batem.**
   Com dois renderizadores (a Meta renderiza a cópia de WhatsApp, o backend
   renderiza a de Telegram) e um só template validado, as duas mensagens saem
   iguais **por construção**. Fora do contrato, divergem em silêncio.

**Consequência de escopo:** botão, teclado inline e formatação rica do Telegram
ficam de fora desta etapa. Entram quando forem declarados **no template**, nunca
como string montada no sender.

### 2.1 O que muda em `integration_whatsapp_unico_ativo`

```sql
create unique index integration_whatsapp_unico_ativo
  on app.integration (tenant_id)
  where active and provider in ('meta_cloud', 'z_api', 'uazapi');
```

⛔ **Não acrescente `'telegram'` a esse predicado.** O índice existe porque
*"dois ativos ao mesmo tempo significa alerta duplicado no telefone do gestor"* —
e isso vale entre provedores **do mesmo canal**. Telegram e WhatsApp são canais
diferentes e **devem** coexistir (é o desenho da §8). Pôr o Telegram ali torna
os dois mutuamente exclusivos e o sintoma é *"liguei o Telegram e o WhatsApp
desligou"*.

O que entra é um índice **irmão**, pelo mesmo motivo e no seu próprio canal:

```sql
create unique index if not exists integration_telegram_unico_ativo
  on app.integration (tenant_id)
  where active and provider = 'telegram';
```

E `telegram` entra nos três checks: `integration_provider_check`,
`alert_queue_provider_check`, `alert_sent_provider_check`.

### 2.2 Os dois índices foram executados lado a lado, não deduzidos

PostgreSQL 16.13, contra um schema mínimo. Oito comportamentos:

| # | Cenário | Resultado |
|---|---|---|
| 1 | **WhatsApp ativo + Telegram ativo, mesmo tenant** | **coexistem** — os índices não se atropelam |
| 2 | segundo provedor de WhatsApp ativo | rejeitado |
| 3 | segundo bot de Telegram ativo | rejeitado |
| 4 | bot **inativo** ao lado do ativo | aceito — o histórico sobrevive |
| 5 | identidade com `contact_id` **e** `employee_id` | rejeitado |
| 6 | identidade **sem** titular | rejeitado — `chat_id` órfão não entra |
| 7 | um titular de cada tipo | aceitos |
| 8 | estado final | 1 WhatsApp ativo, 1 Telegram ativo, 1 Telegram inativo |

A linha 1 é a razão de a tabela existir: é exatamente o que quebra se alguém
acrescentar `'telegram'` ao predicado do índice de WhatsApp, e o sintoma —
*"liguei o Telegram e o WhatsApp desligou"* — chega como bug de produto, não
como erro de migration. **Virou `scripts/86_teste_canais_exclusividade.sql`** (onda 1 do C3, 15/09/2026), no lugar onde a suíte de banco roda os outros.

---

## §3. O `chat_id`: identidade de mensageria, não coluna de cadastro

Decisão do owner: o Telegram alcança **responsáveis e colaboradores**. Isso traz
um identificador novo por pessoa, e onde ele mora decide o resto.

### 3.1 Por que não é uma coluna

`telegram_chat_id` em `app.contact` **e** em `app.employee_pii` seria duas
colunas, dois caminhos no sender, e — o que importa — **perderia o que o dado
realmente é**. Um `chat_id` não é um atributo da pessoa como o CPF. É um
**registro de consentimento**: tem data, tem origem (ela iniciou o bot), e é
revogável (ela bloqueia o bot). Coluna não guarda nada disso.

```sql
create table if not exists app.messaging_identity (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references app.tenant(id) on delete cascade,
  channel      text not null check (channel in ('telegram')),
  contact_id   uuid references app.contact(id)  on delete cascade,
  employee_id  uuid references app.employee(id) on delete cascade,
  external_id  text not null,                 -- chat_id do Telegram
  opted_in_at  timestamptz not null default now(),
  revoked_at   timestamptz,
  revoked_reason text,
  constraint messaging_identity_um_titular
    check ((contact_id is null) <> (employee_id is null))
);
```

`check ((contact_id is null) <> (employee_id is null))` — exatamente um titular,
nunca os dois, nunca nenhum.

**Sem delete físico** (regra 6 estendida): revogar preenche `revoked_at`. Quem
bloqueou o bot e voltou tem duas linhas e a história fica legível.

### 3.2 Domínio e superfície

O `chat_id` é dado pessoal: identifica a pessoa e a liga a uma conta de
Telegram. **Domínio `pii`**, mesma matriz do CPF — `owner`, `personnel`, `hr`.

> ✅ **Decisão do dono, 15/09/2026, mais dura que a linha acima:** nenhum
> papel do painel lê `app.messaging_identity` nem `app.messaging_invite` —
> nem `owner`. As duas tabelas têm RLS ligada e **zero policy**, a régua de
> `app.integration_secret`; só `service_role` (o sender e o webhook) as
> alcança. A matriz do CPF descreve quem *poderia* ver; ninguém precisa.

Mas a tela não precisa dele. Ela precisa de **quantos aderiram**, por unidade.
Então:

- linha individual: só pelo Caminho 2, e na prática só o sender a lê;
- `public.fn_telegram_adhesion` devolve **contagem por unidade** — aderiram,
  faltam, revogaram. Nome nenhum, `chat_id` nenhum.

⛔ **O `chat_id` nunca aparece em tela, log, export ou resposta de API.** Mesma
régua da conta bancária da etapa DP.

### 3.3 O link de adesão **é** a credencial — e é aqui que dá errado

O Telegram vincula por deep link: `https://t.me/<bot>?start=<token>`. O bot
recebe `/start <token>`, resolve para a pessoa e grava o `chat_id`.

> **Quem abrir o link vira o destinatário daquela pessoa.** O token no link é a
> autenticação inteira. Encaminhou o WhatsApp para o grupo da família, tirou
> print no grupo da unidade — quem clicar primeiro passa a receber os alertas
> individuais daquele colaborador: vencimento de CNH, falta, advertência.

Isso **não tem paralelo no WhatsApp**, onde o endereço é o número que o
empregador já tem e a operadora já verificou. É risco novo, criado por esta
etapa, e a forma tem que respondê-lo:

```sql
create table if not exists app.messaging_invite (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references app.tenant(id) on delete cascade,
  channel      text not null check (channel in ('telegram')),
  contact_id   uuid references app.contact(id)  on delete cascade,
  employee_id  uuid references app.employee(id) on delete cascade,
  token_hash   text not null,               -- hash, nunca o token
  expires_at   timestamptz not null,
  used_at      timestamptz,
  created_at   timestamptz not null default now(),
  constraint messaging_invite_um_titular
    check ((contact_id is null) <> (employee_id is null))
);
create unique index if not exists messaging_invite_token_uk
  on app.messaging_invite (token_hash);
```

Cinco regras, e nenhuma é opcional:

1. **Uso único.** `used_at` preenchido invalida. Segundo clique não vincula.
2. **Validade curta** — dias, não meses. Convite velho circulando é o vetor.
3. **`token_hash`, nunca o token.** Vazamento do banco não entrega vínculos.
4. **O convite viaja pelo canal já verificado.** O link vai **por WhatsApp, para
   o número que o empregador já tem em cadastro.** A cadeia de confiança fica:
   empregador tem o número → a operadora entrega naquele aparelho → a pessoa
   clica → o `chat_id` fica ligado. É o padrão da verificação por e-mail, e é o
   que torna o vínculo tão confiável quanto o cadastro já era.
5. **Vínculo visível e revogável.** A ficha mostra *"Telegram vinculado em
   DD/MM"* e um botão de desvincular. Vínculo silencioso não tem como ser
   contestado por quem foi prejudicado.

### 3.4 O irmão da regra 7

A regra 7 diz: **alerta de conteúdo individual nunca vai para grupo**, porque
*"exposição nominal de colaborador em grupo é risco trabalhista"*.

Um `chat_id` sequestrado não é um grupo, e o `util.validate_alert_target` não o
pega — ele olha `contact.type`. Mas o dano é o mesmo: conteúdo individual na tela
de quem não é o titular. **É a mesma regra num destinatário que a regra não
previa**, porque quando ela foi escrita todo destinatário era um número
verificado.

⛔ **Parada obrigatória:** a §3.3 inteira é a mitigação. Se alguma das cinco
regras for cortada por custo, isso é decisão de owner com o risco nomeado — não
simplificação de implementação.

---

## §4. Migrações

Cinco. Nomes no padrão das etapas anteriores.

- **`ch_telegram_provider`** — `telegram` nos três checks;
  `integration_telegram_unico_ativo`; comentário em `app.integration.provider`
  explicando a terceira família da §1.1.
- **`ch_messaging_identity`** — `app.messaging_identity` + `app.messaging_invite`,
  RLS, domínio `pii`. ⛔ **Parada obrigatória:** duas tabelas novas com policy.
- **`ch_channel_health`** — `app.channel_health` (§7).
- **`ch_readiness_fn`** — `public.fn_channel_readiness` generalizando
  `fn_whatsapp_readiness` para os quatro provedores.
  ⚠️ **Não apague `fn_whatsapp_readiness`** nesta migration: alguém pode estar
  chamando. Deprecie com `comment on`, remova numa migration posterior, depois de
  medir que ninguém chama. É a lição do `sync-fotos` — *"medir que pararam"* é um
  passo, não uma formalidade.
- **`ch_adhesion_fn`** — `public.fn_telegram_adhesion`, contagem por unidade.

⚠️ `trg_lock_down_new_function` **não cobre `public`**. As duas RPCs precisam do
`grant execute` **escrito** na migration.

---

## §5. A tela de Conexões

Decisão do owner: **grava credencial, validando antes**.

### 5.1 O caminho, que já existe e não pode ser contornado

`app.integration_secret` guarda **só o ponteiro** para o Vault, e o comentário
da tabela é categórico: *"Nenhum role do painel lê esta tabela — nem owner."*

Logo:

```
navegador → FastAPI (Caminho 2) → valida no provedor → vault.secrets → ponteiro
```

⛔ O navegador **nunca** toca a credencial com a chave anônima. Não há policy a
escrever; a ausência dela é o desenho.

### 5.2 Validar antes de gravar

Do DeskcommCRM, e a razão está escrita lá:

> *"Gravar primeiro e descobrir depois é o que faz o operador achar que conectou
> e só entender que não na primeira mensagem que não sai — com o lead do outro
> lado esperando."*

No OperaX o do outro lado é um gestor esperando um alerta de desvio. Mesma
falha, consequência diferente.

- `meta_cloud`: chamada à Graph API com o token.
- `telegram`: `getMe` no token do bot — devolve o `username`, que a tela mostra
  (*"conectado como @FastParkAlertasBot"*). Confirmação legível para humano.
- `z_api` / `uazapi`: chamada de status do provedor.

**Nada é gravado se a validação falhar.**

### 5.3 O segredo nunca volta

*"Uma vez gravado, a tela mostra que existe, não qual é."* `GET` devolve
`{ configurado: true, atualizado_em, identificacao_publica }` — nunca o valor.

⛔ **E a mensagem de erro da validação não ecoa o token.** Provedor que devolve
o token no corpo do erro tem o corpo descartado; o log recebe o código, não a
resposta. Vale a regra permanente: valor de variável de ambiente e segredo não
entram em documento, commit, log ou resposta.

### 5.4 Um defeito visível nas telas do DeskcommCRM — não copie

Nas capturas, **"ID do número de telefone"** está preenchido com um e-mail, e
**"Conta"** do provedor parceiro também. É o autofill do navegador despejando
e-mail em campo que quer identificador numérico: falta `autocomplete` adequado e
falta validação de formato.

O `POST` valida contra a Meta, então nada errado é gravado — mas o operador
recebe um erro da Graph API em vez de *"isto não parece um ID de número"*.
Barato de acertar na origem, caro de diagnosticar depois.

### 5.5 O que a tela mostra que o OperaX já sabe e não mostra

`fn_whatsapp_readiness` devolve `templates_total`, `templates_approved`,
`rules_blocked` e `ready`. **É a aba de saúde inteira, pronta.** A tela lê e
mostra *"3 regras bloqueadas: template `deviation_individual` está `pending` na
Meta"* — a frase que hoje só existe dentro de uma função que ninguém chama.

A aba de templates espelha o *"Sincronizar"* deles: traz `meta_status` da WABA
para `app.message_template`. É o que fecha o laço entre `ready = false` e a ação
que conserta.

---

## §6. O webhook — superfície nova e não autenticada

O Telegram entrega updates por webhook. É um endpoint **público por
construção**: quem chama é o Telegram, não um usuário com JWT.

- **Segredo no header.** `setWebhook` aceita `secret_token`; o Telegram o devolve
  em `X-Telegram-Bot-Api-Secret-Token`. Requisição sem ele é descartada **antes**
  de qualquer parse.
- **Caminho com token rotativo**, como o `webhook_path_token` deles — e a lição
  junto: desconectar **rotaciona** o token de propósito, porque é o que corta a
  entrega da plataforma. Reconectar **não** devolve o endereço antigo; a tela
  precisa mostrar o novo.
- **O corpo é dado hostil.** Só `/start <token>` é tratado. Qualquer outro update
  é registrado e descartado — o bot **não conversa**. Ele não tem o que
  responder: o assistente não está do outro lado (`SPEC-AGENTE.md` §6.1), e um
  bot que responde é o primeiro passo para ligar os dois.
- **Rate limit por IP e por token**, e nenhum eco do corpo no log de erro.

⛔ **Parada obrigatória:** endpoint público novo sem autenticação de usuário.

---

## §7. Saúde do canal — o vigia que pergunta

A melhor página do DeskcommCRM nesta área, e o argumento é bom demais para
parafrasear:

> *"O webhook emudece exatamente quando mais falta. Ele avisa em segundos
> enquanto o transporte está vivo; quando o transporte morre (…) não chega evento
> nenhum — e 'nenhum evento' é indistinguível de 'tudo bem'. (…) Foi assim que
> uma desconexão real passou horas despercebida numa instalação de verdade."*

`app.channel_health` — `integration_id`, `status`, `checked_at`,
`status_changed_at`, `detail`. `status_changed_at` só avança quando o status
**muda**, para medir tempo no estado.

É a mesma disciplina de `public.fn_data_freshness` (migration 12) aplicada ao
canal: no OperaX **dado sem idade não é dado**, e conexão sem idade também não.
E a simetria vai além do estilo — as duas respondem à mesma pergunta (*"isto
ainda vale?"*) sobre as duas metades do produto: a que entra e a que sai.

⛔ **O vigia não religa.** Direto deles, e no OperaX vale mais ainda:

> *"Religar sozinho uma conexão que caiu por bloqueio da plataforma é a receita
> para transformar uma suspensão temporária em definitiva."*

`DECISAO-WHATSAPP.md` §1 diz que o banimento dos não oficiais é **do número,
permanente, sem recurso**. Reconexão automática num número em bloqueio é o
caminho mais curto para o cenário em que *"quem explica é a EURECA"*.

---

## §8. Roteamento: qual canal para quem

Os dois canais coexistem (§2.1). A regra:

> **Telegram se houver identidade vigente; WhatsApp caso contrário.**

Sem tela de preferência, sem coluna de escolha. Degrada sozinho: quem não
aderiu continua recebendo por WhatsApp exatamente como hoje, e a adesão é uma
melhoria silenciosa por pessoa.

Três consequências:

1. **O ganho é medível e é o argumento comercial.** Cada responsável que adere
   sai do número de WhatsApp do cliente. Menos volume no número = menos
   exposição ao banimento que a `DECISAO-WHATSAPP.md` §1 descreve. **O Telegram
   não é só mais um canal; é redução de risco de banimento.**
2. **A mesma mensagem sai por dois renderizadores** — a Meta renderiza a de
   WhatsApp, o backend renderiza a de Telegram — a partir de **um** template
   validado. Iguais por construção (§2, item 3).
3. **`app.alert_sent.provider` passa a ter quatro valores**, e o relatório de
   entrega quebra por canal sem trabalho novo.

---

## §9. O que **não** vem do DeskcommCRM

- **`channel_sessions` como tabela.** O OperaX já tem `app.integration` +
  `app.integration_secret` + Vault, que é um modelo melhor (o segredo não está na
  linha). A tela nova assenta no que existe.
- **QR Code na tela.** `z_api` e `uazapi` conectam por QR no painel **deles**.
  Espelhar isso aqui é construir um segundo painel de um produto de terceiro.
  A tela do OperaX mostra **estado**; conectar continua sendo no provedor.
- **Reconexão automática** (§7).
- **Bot conversacional.** O webhook trata `/start` e nada mais (§6).
- **Grupos no Telegram.** A regra 7 vale igual, e o Telegram torna grupo trivial
  de criar. Fora desta etapa, e quando entrar precisa passar por
  `util.validate_alert_target` com `type = 'telegram_group'` — que **não existe
  hoje** e precisa ser criado junto, ou a regra 7 fica cega no canal novo.

---

## §10. Aberto — do owner

1. **Bot por tenant ou da plataforma?** Recomendo **por tenant**:
   `app.integration` já é por tenant, o token vive no Vault do jeito certo, e o
   cliente vê o nome dele (`@FastParkAlertasBot`). Bot único de plataforma
   concentra: um token comprometido expõe as mensagens de todos.
2. **Prazo de validade do convite.** Sugiro **7 dias**, alinhado com o prazo do
   ADR-018. Curto o bastante para o link não circular, longo o bastante para
   quem estava de folga.
3. **Adesão dos 176 é projeto, não configuração.** Está isolada no S4 de
   `SPRINTS-CANAIS.md` e **não bloqueia** os outros sprints. Precisa de uma
   decisão sua que não é técnica: **a adesão é voluntária ou esperada?** Muda o
   texto do convite, e muda o que acontece com quem não adere — que na resposta
   voluntária é *nada*, e continua no WhatsApp para sempre.
