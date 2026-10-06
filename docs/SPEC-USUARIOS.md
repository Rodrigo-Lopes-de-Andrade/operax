# OperaX — tela de cadastro de usuários

**Origem:** pedido do owner em 04/10/2026. Fecha a pergunta 10 da
`SPEC-TECNICA.md` (*"Gestor terá login? → Convite de usuário e escopo"*).

**Versão 2.1, de 04/10/2026** — §4, §4.1, §5.2, U2 e §8.1 ajustados ao estado
real antes do primeiro despacho (ver a nota no fim da §4).

**Versão 2, de 04/10/2026.** A v1 passou por auditoria de dois agentes sem
contexto, que rodaram o schema em vez de lê-lo. **Quatro afirmações dela estavam
erradas, duas invertidas.** A errata é a §0 — leia antes, porque a v1 circulou.

---

## §0. Errata da v1

| O que a v1 dizia | O que é verdade | Como se descobriu |
|---|---|---|
| *"sem o `grant execute` a função nasce inacessível com 403"* | **Invertido.** Função nova em `public` nasce com `EXECUTE` para `PUBLIC`, e `anon` tem `USAGE` em `public`. Ela nasce **chamável pela chave anônima**. Falta um `revoke`, não um `grant`. | `has_function_privilege('anon', …) = true` sem grant nenhum; `false` depois do par `revoke`+`grant` |
| *"o painel escreve direto pelo Caminho 1, com a chave anônima"* | **Falso.** O schema `app` não é exposto ao PostgREST e `anon` não tem `USAGE` nele: `permission denied for schema app`. Quem escreve é a sessão **`authenticated`** do backend. | insert como `anon` negado **antes** de qualquer migration |
| *"`app.audit_log` só aceita escrita de `service_role`"* | **Falso.** `service_role` não tem GRANT nenhum nela, nem SELECT. `rolbypassrls` ignora RLS, não ignora GRANT. Quem grava é o **owner da tabela** — ou seja, uma função `security definer`. | `permission denied for table audit_log` como `service_role` |
| *"`viewer` é o único papel sem domínio sensível"* | **São quatro:** `regional_manager`, `unit_supervisor`, `operations_manager`, `viewer`. O dicionário diz isso na linha 31. | consulta a `app.domain_permission` |

A conclusão de projeto da v1 sobreviveu — as policies `ALL` devem cair — mas
**pelo motivo errado**, e o gate que ela escreveu para provar isso **já passava
antes de qualquer trabalho**. Está corrigido na §7.

---

## §1. O que esta tela é

Não é um CRUD de pessoas. **É a superfície que concede acesso a salário, PII,
saúde e disciplinar.** Conceder papel em `app.tenant_member` concede, por
`app.domain_permission`, os domínios daquele papel.

Cada campo é uma decisão de segurança, e o modo de falha que importa não é o
erro — é a concessão silenciosa.

## §2. Decisões do owner (04/10/2026)

| # | Decisão |
|---|---|
| 1 | **Só `owner` concede papel.** `hr` e `personnel` administram convite, escopo e desativação. |
| 2 | **O admin do cliente convida por e-mail.** O Supabase manda o convite; a pessoa define a própria senha. |

### 2.1 O que as duas juntas implicam

O convidado nasce **`viewer`**. `hr` e `personnel` **preparam** (convite e
escopo); o `owner` **autoriza** (papel), e esse é o único ato que concede
privilégio.

⚠️ `viewer` **não** é o único papel sem domínio sensível — são quatro (§0). A
escolha continua certa por outro motivo: é o único que não tem domínio **nem**
atalho de escopo por papel (§3.2).

⚠️ **Custo:** todo supervisor novo espera o owner. Se incomodar, a revisão
natural é *"qualquer admin concede qualquer papel menos `owner`"*. Registrado
como saída, não aplicado.

## §3. Escopo: dois curingas, e a v1 só fechou um

### 3.1 O curinga medido, e o irmão que a v1 não viu

`util.can_see_unit` testa dois curingas independentes; `util.can_see_company`
testa **só um**, e não olha `unit_id`:

```sql
-- can_see_unit
and (e.company_id is null or e.company_id = u.company_id)
and (e.unit_id    is null or e.unit_id    = u.id)
-- can_see_company
and (e.company_id is null or e.company_id = emp.id)     -- só isto
```

Executado em PostgreSQL 16.13 com as duas funções copiadas verbatim da
`11b_rename_pt_en.sql`, papel `unit_supervisor`, 2 unidades em 3 empresas:

| Linha em `app.user_scope` | Unidades | Empresas |
|---|---|---|
| nenhuma | 0 | 0 |
| **só `unit_id`** (o caso normal da tela) | 1 ✓ | **3** ⚠️ |
| `unit_id` **e** `company_id` | 1 ✓ | 1 ✓ |

**A linha que a tela criaria para todo supervisor concede visibilidade de todas
as empresas do tenant.** Alcança `company_read` (razão social e CNPJ),
`department_read` e `payroll_charge_read`.

A v1 fechou o caso dos dois nulos, que era acidental, e deixou aberto o caso de
`company_id` nulo, que seria **intencional e repetido**.

### 3.2 E "zero linha é seguro" vale para 5 dos 9 papéis

As duas funções têm atalho por papel **antes** de olhar `user_scope`:

```sql
tm.role in ('owner','executive','hr','personnel')  or exists (...)
```

Com zero linha de escopo: `owner`, `executive`, `hr` e `personnel` enxergam o
tenant inteiro. **`executive` não é `util.is_admin`** e mesmo assim enxerga tudo.

⛔ Consequência para a tela: para esses quatro papéis o resumo de escopo da §6
**mentiria**. Mostrar "Empresa Alfa" para quem enxerga três é pior que não
mostrar nada.

### 3.3 A correção, e por que ela não toca nas funções

```sql
alter table app.user_scope
  add constraint escopo_nao_vazio check (unit_id is not null or company_id is not null),
  add constraint escopo_unidade_tem_empresa check (unit_id is null or company_id is not null);

create unique index if not exists user_scope_sem_duplicata
  on app.user_scope (user_id, tenant_id, coalesce(company_id,'00000000-0000-0000-0000-000000000000'::uuid),
                                          coalesce(unit_id,   '00000000-0000-0000-0000-000000000000'::uuid));
```

A segunda constraint é o conserto da §3.1: **unidade sempre acompanhada da
empresa dela**. Medido — com `company_id` preenchido, o supervisor passa de 3
empresas para 1, **sem alterar nenhuma função**.

📌 **Por que não consertar `can_see_company`.** Ela é recriada em
`11b_rename_pt_en.sql`, depois da `04`. Um conserto na 04 é apagado no próximo
`db reset`, sem erro. Mexer nela exige migration nova e revalidar todo caminho
que a usa. A constraint resolve com uma linha e nenhum risco de regressão.

⚠️ **Alternativa, se você preferir:** fechar `can_see_company` em migration nova
para exigir a empresa da unidade quando houver `unit_id`. Mais correto na raiz,
mais caro de validar. **Recomendo a constraint; a decisão é sua.**

⚠️ **As duas constraints podem falhar ao ser criadas.** Se falharem, existe hoje
escopo-curinga em produção. **É o achado, não o obstáculo** — pare e reporte, e
não apague as linhas: quem tinha acesso a quê é evidência.

⚠️ **Custo da constraint, declarado:** hoje a linha de dois nulos acompanha
empresa nova automaticamente. Depois dela, "todas as unidades" vira uma linha por
empresa — **um retrato, não uma regra**. Empresa nova não entra sozinha no escopo
de ninguém. Previsível e preferível ao silêncio, mas precisa estar na tela.

## §4. O que existe hoje

| Objeto | Estado |
|---|---|
| `app.tenant_member` | `(tenant_id, user_id)`, `role`, `active`, `created_at`. Só a policy `tenant_member_read` (SELECT); `authenticated` **sem** INSERT/UPDATE/DELETE. **Sem** `invited_by` nem `deactivated_at` |
| `app.user_scope` | `company_id`/`unit_id` anuláveis, **sem constraint**, **sem unique**. Só a policy `escopo_read` (SELECT); `authenticated` **sem** escrita |
| `app.domain_permission` | Policy **só SELECT**. Não editável pelo painel, e está certo |
| `app.audit_log` | `action` com **CHECK fechado**: `insert, update, delete, login, export, sensitive_query`. Nenhuma policy de insert. **Nada no produto grava nela hoje** |
| `util.is_admin` | `owner`, `hr`, `personnel` |
| `auth.users` | Supabase Auth. Não exposto ao PostgREST; `CLAUDE.md` proíbe migration |
| Tela | **não existe** |

📌 **Nota da v2.1 (04/10/2026).** A v2 descrevia `tenant_member_admin` e
`escopo_admin` como policies `ALL`. **Elas já não existem:** a etapa de alçada
(P1.2b, `20260930225115_alcada_revoke_writes.sql`) as removeu junto com os
revokes de tabela, por decisão do owner de 30/09, e isso está em produção desde
04/10. A condição de parada 2 divergiu; o owner decidiu ajustar a etapa e seguir.

### 4.1 ✅ As policies `ALL` já caíram — na etapa de alçada

O caminho que elas abrem **não** é a chave anônima (§0). É a sessão
`authenticated` que o backend assume (`core/tenant.py` → `set_config('role',
'authenticated')`). Medido: como `authenticated` com um `owner`, o insert direto
em `app.tenant_member` **passou** antes do drop e **falhou** depois.

E toda guarda deste documento — último owner, papel só por owner, nada de delete
— vive nas RPCs. Uma escrita direta por essa sessão **pula todas**.

```sql
drop policy if exists tenant_member_admin on app.tenant_member;
drop policy if exists escopo_admin        on app.user_scope;

-- A policy era metade. A outra metade é o grant de tabela, que sobrevive a ela.
revoke insert, update, delete on app.tenant_member, app.user_scope from authenticated;
```

✅ **Feito pela P1.2b**, com asserções negativas no `98` (`hr` se promovendo a
`owner`, `personnel` a `hr`, inserir membro, mexer em escopo — todas exigindo
`permission denied for table`). Esta etapa **não** repete o drop; a U2 só
confirma que continua assim.

📌 **Honestidade de escopo:** existem **21** tabelas em `app` com policy `ALL`
para `authenticated`, entre elas `employee_pii` e `employee_compensation` — a PII
e o salário que a §1 define como o que está em jogo. A P1.2b fechou três delas
(`tenant_member`, `user_scope`, `employee`); a contagem atual precisa ser
remedida. As que restam ficam, e isso é escolha registrada, não descuido. Ver §9.

## §5. A forma

### 5.1 `usuarios_escopo_constraint` — as duas constraints e a unique (§3.3)

Primeira migration, **sozinha**: ela pode falhar por achado, e falhar sozinha é
o que torna o achado legível.

### 5.2 ~~`usuarios_fecha_escrita_painel`~~ — não existe mais (§4.1)

Os drops e os revokes já estão em `20260930225115_alcada_revoke_writes.sql`.
Nenhuma migration nova; a U2 verifica que continuam valendo.

### 5.3 `usuarios_colunas_da_lista`

```sql
alter table app.tenant_member
  add column if not exists invited_by      uuid references auth.users(id),
  add column if not exists deactivated_at  timestamptz;
```

A v1 mandava a lista mostrar "quem convidou" e "a data" da inativação sem que
nenhuma coluna existisse. Ou elas entram, ou a §6 some.

### 5.4 `usuarios_rpc` — quatro funções

**Todas** `security definer set search_path = ''`, e **todas recebem
`p_tenant_id`**. A v1 não recebia, e isso tornava uma guarda inimplementável: os
claims da sessão carregam só `sub` e `role` (`core/tenant.py`), **sem tenant**.
Um usuário membro de dois tenants deixava `member_not_found` sem referente —
reproduzido, com resultado `AMBÍGUO: 2 memberships`. O precedente da casa
(`fn_publish_assistant_prompt`) já recebe `p_tenant_id`.

**Forma da recusa, para as quatro:** `raise exception` com `errcode = 'P0001'` e
`message` = o código. É a convenção do repositório.

**Gravação em `app.audit_log`, para as quatro:** `action = 'update'` — exceto o
convite, que grava `'insert'` (também no CHECK, e mais fiel; v2.1) — (valor do
CHECK existente — **não alargar o CHECK**), `entity = 'tenant_member'` ou
`'user_scope'`, com `antes` e `depois`. A função grava por ser `security
definer` e rodar como o owner da tabela; **não é preciso policy de insert nova**,
e criar uma seria parada obrigatória sem motivo.

| Função | Quem | Recusas |
|---|---|---|
| `fn_convidar_usuario(p_tenant_id, p_user_id, p_scope jsonb)` | `hr`/`personnel`/`owner` | `not_admin`, `ja_e_membro`, `conta_em_outro_cliente`, `escopo_vazio`, `escopo_invalido`, `escopo_sem_empresa`, `empresa_fora_do_tenant`, `unidade_fora_da_empresa` |
| `fn_definir_papel(p_tenant_id, p_user_id, p_role)` | **só `owner`** | `not_owner`, `member_not_found`, `ultimo_owner` |
| `fn_definir_escopo(p_tenant_id, p_user_id, p_scope jsonb)` | `hr`/`personnel`/`owner` | `not_admin`, `member_not_found`, `escopo_vazio`, `escopo_invalido`, `escopo_sem_empresa`, `empresa_fora_do_tenant`, `unidade_fora_da_empresa` |
| `fn_desativar_membro(p_tenant_id, p_user_id)` | `hr`/`personnel`/`owner`; **`owner` só por `owner`** (decisão de 05/10) | `not_admin`, `e_voce_mesmo`, `member_not_found`, `owner_so_por_owner`, `ultimo_owner` |

As recusas estão na ordem em que a função as dá (v2.1, conforme
`20261005011138_usuarios_rpc.sql`). `p_scope` é uma lista não vazia de
`{company_id, unit_id?}`, só com essas duas chaves e valores string; "todas as
unidades" é uma entrada por empresa. Antes do lock, quem não é do tenant recebe a
recusa de papel sem esperar.

⛔ **Um cliente por usuário (U3, decisão de 05/10/2026).** Depois de
`ja_e_membro`, o convite toma `pg_advisory_xact_lock` por `user_id` e recusa
`conta_em_outro_cliente` se a pessoa tem vínculo `active` em **qualquer** outro
tenant — inclusive tenant inativo, que pode voltar. A trava por usuário
serializa dois clientes convidando a mesma pessoa; a trava por tenant não
alcança essa corrida. Sem índice único: o `98` prova, de propósito, um usuário
ativo em dois tenants.

⚠️ **`fn_convidar_usuario` recebe `p_user_id`, não `p_email`.** A v1 mandava a
função resolver e-mail → identidade, o que é impossível: `tenant_member.user_id`
é `not null` com FK para `auth.users`, e a identidade nasce no Admin API, fora do
banco. A **fronteira é esta**, e precisa estar escrita porque dois agentes
competentes a desenhariam diferente:

```
tela → FastAPI → Admin API do Supabase (cria/convida, devolve user_id)
                   ↓
              fn_convidar_usuario(tenant, user_id, escopo)
```

⛔ **Ordem:** a RPC roda **depois** do Admin API, e se ela recusar o convite já
foi enviado. Então `ja_e_membro` e `conta_em_outro_cliente` são verificados
**antes** de chamar o Admin API, numa leitura prévia — que só evita o e-mail;
quem garante é a RPC, sob a trava. Convidar e recusar depois manda e-mail para quem não
deveria recebê-lo.

⛔ **`fn_definir_escopo` valida `escopo_vazio` ANTES de apagar o anterior.**
Apagar e falhar na inserção deixa a pessoa sem escopo nenhum, em silêncio.

### 5.5 ⛔ O par `revoke` + `grant`, não o `grant` sozinho

A v1 tinha isto invertido (§0). Para **cada uma** das quatro:

```sql
revoke execute on function public.fn_definir_papel(uuid, uuid, app.user_role) from public, anon;
grant  execute on function public.fn_definir_papel(uuid, uuid, app.user_role) to authenticated, service_role;
```

Sem o `revoke`, a função nasce chamável por `anon` — medido, `anon` chegou numa
RPC `security definer` e só foi barrado pela checagem interna de papel. É a
camada única que esta etapa inteira existe para não ter.

📌 ~~O check 9 varre só `util`~~ — **falso, corrigido na v2.1:** o check 9 do
`99_verificacao_rls.sql` varre `util` **e** `public` desde 07/09/2026 (linha 199).
Medido na U2: com `grant execute` a `anon` numa das quatro funções, o 99 reprova
com `função insegura -> public.fn_definir_papel(anon pode executar)`.

### 5.6 Senha: a tela nunca toca

Ninguém define, vê, reseta ou transporta senha. A ação chama-se **"reenviar
convite"**, não "resetar senha" — o nome importa, porque o segundo sugere que
alguém do outro lado sabe qual é.

## §6. A tela

**Lista.** Nome, e-mail, papel, escopo, status, quem convidou. Nome e e-mail
vivem em `auth.users`, que não é exposto ao PostgREST: a lista vem de uma rota
FastAPI (`GET /usuarios`) que lê com `service_role` e revalida papel — o mesmo
padrão de `GET /me`. Inativos aparecem em cinza com `deactivated_at`.

⛔ **Para `owner`, `executive`, `hr` e `personnel` a coluna de escopo diz
"todas as unidades (pelo papel)"**, nunca o conteúdo de `user_scope` (§3.2).

**Convidar.** E-mail + escopo. Sem campo de papel: nasce `viewer`, e a tela diz
por quê.

⛔ O seletor de escopo não tem estado vazio válido, e **unidade sempre grava a
empresa dela junto** (§3.3). "Todas as unidades" grava uma linha por empresa, e a
tela avisa que empresa nova não entra sozinha.

**Detalhe.** Papel (seletor habilitado só para `owner`), escopo, desativar,
reenviar convite.

**E a matriz de domínios do papel selecionado, em leitura**, vinda de
`app.domain_permission` — não de constante no código. Escolher `hr` mostra ali
*"enxerga CPF, RG, endereço, filiação"*. Quem concede precisa ver o que concede
no momento de conceder.

⚠️ Quatro papéis têm **zero** domínio: a matriz fica vazia para eles, e a tela
precisa dizer "nenhum domínio sensível" em vez de mostrar nada.

## §7. Sprints

**U1 — As constraints.** §5.1 sozinha.
*Gate:* `scripts/teste_escopo_curinga.sql` com as **seis** linhas da §3, **papel
fixado em `unit_supervisor`** e fixture declarada (2 unidades, 3 empresas).
⚠️ Sem fixar o papel, o atalho da §3.2 responde e o teste mede outra coisa.
Positivo obrigatório: **escopo por empresa continua vendo as unidades daquela
empresa** — uma correção que quebre isso passa pelos negativos.

**U2 — As RPCs.** §5.3 + §5.4 + §5.5 (a §5.2 já foi feita pela P1.2b).
⛔ Parada: as quatro RPCs em `public`.
*Gate — quatro negativos e três positivos:*
- insert direto em `app.tenant_member` **como `authenticated` com um `owner`** é
  recusado (⚠️ como `anon` isso já falha hoje e não prova nada). Já é verdade
  desde a P1.2b: aqui é **regressão**, não prova de trabalho novo;
- **nenhuma das quatro RPCs é executável por `anon`** (`has_function_privilege`);
- `fn_definir_papel` por `hr` → `not_owner`;
- `fn_definir_escopo` por `unit_supervisor` → `not_admin`, **e o escopo não mudou**;
- **positivo:** `owner` define papel → papel gravado **e** uma linha em
  `audit_log` com `antes` e `depois` não nulos;
- **positivo:** `fn_desativar_membro` → `active = false`, linha preservada,
  `deactivated_at` preenchido;
- **positivo:** `fn_definir_escopo` com escopo vazio → `escopo_vazio` **e as
  linhas anteriores continuam lá** (contar antes e depois).

**U3 — Convite e lista.** §5.4 (`fn_convidar_usuario`) + rota `GET /usuarios` +
tela de lista e convite.
*Gate:* convidado chega como `viewer`; **a lista mostra nome, e-mail e quem
convidou** do recém-convidado; o seletor não submete vazio nem unidade sem
empresa; e **nenhuma resposta de API contém senha ou token de convite** — teste
que varre o JSON.

**U4 — Detalhe e matriz.**
*Gate:* para `hr` o seletor está desabilitado **e a rota recusa**; virar uma
linha de `app.domain_permission` no banco **muda a matriz na tela** (par fixado:
`viewer` → `hr`); e os quatro papéis de atalho mostram "todas as unidades (pelo
papel)".
⚠️ `ultimo_owner` e `e_voce_mesmo` são gate da **U2**, não desta: são SQL, e o
`nextjs-developer` não pode consertá-los.

## §8. Perguntas abertas

1. ⛔ **Break-glass: e se o único `owner` ficar indisponível?** Com um owner só,
   ninguém mais concede papel (decisão 1), `ultimo_owner` impede rebaixá-lo,
   `e_voce_mesmo` impede que ele se desative, e a §4.1 **remove o último caminho
   por onde um `hr` poderia promover substituto**. Hoje não há saída por dentro
   do produto.
   ✅ **Respondida pelo owner em 04/10/2026: SQL de operador.** Nada novo no
   produto; promover substituto é procedimento documentado de operador EURECA,
   com linha em `app.audit_log`. A regra prática é manter **dois** owners ativos
   — o caso da FastPark desde 04/10 (medido: 2 owners, 1 personnel).
2. **O usuário do painel é a mesma pessoa que `app.contact`?** Quem recebe alerta
   é `contact`; quem faz login é `tenant_member`. Não há elo, e quem sai da
   empresa precisa sumir dos dois.
3. **Fechar `can_see_company` na raiz, em vez da constraint?** §3.3.
4. **Colaborador acessa o painel?**
5. ✅ **Reativar um membro desativado — respondida em 05/10/2026: procedimento de
   operador**, SQL com linha em `app.audit_log`, como o break-glass. O SQL
   passa por fora da RPC, então confere antes, sob a mesma trava por usuário,
   que a pessoa não está ativa em outro tenant — reativar quem hoje é de outro
   cliente recria o vínculo ambíguo. Nada no
   produto; a tela avisa que desativar é definitivo. `invited_by` fica sem
   `on delete` de propósito: apagar no Auth quem já convidou alguém falha, e a
   autoria do convite se preserva.

## §9. O que não entra

- **As outras 19 policies `ALL`** de `app`, incluindo `employee_pii` e
  `employee_compensation` (§4.1). Fica para etapa própria, e está registrado
  aqui para não parecer esquecimento.
- Edição da matriz `role → domínio` pela tela.
- Delete de membro: `active = false`, sempre.
- Papel novo; SSO; login social.
