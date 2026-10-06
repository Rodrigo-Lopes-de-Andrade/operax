# OperaX — sprints do cadastro de usuários

Implementação de `SPEC-USUARIOS.md` (v2.1). **Só o orquestrador escreve status
neste arquivo.** Teto: dois ciclos de correção por sprint; a U1 não tem ciclo.
Ordem serial: U1 → U2 → U3 → U4.

Revisão de toda sprint: `code-reviewer` **e** `guardiao-do-acesso`. O
`code-reviewer` lê o bloco da sprint **neste arquivo**, não em `SPRINTS.md`.

---

## U0 — Reconferência · ✅ 04/10/2026

| # | Condição de parada | Resultado |
|---|---|---|
| 1 | `docs/SPEC-USUARIOS.md` no repositório | ✅ presente |
| 2 | As quatro afirmações da §4 batem com o dicionário | ❌ **diverge uma**: `tenant_member_admin` e `escopo_admin` **não existem** — a P1.2b da alçada as removeu (e os revokes de tabela) por decisão de 30/09, em produção desde 04/10. Passam: `domain_permission` só com `domain_permission_read` (SELECT); `util.is_admin` = `owner, hr, personnel`; `audit_log.action` com CHECK de seis valores |
| 3 | Elenco | ✅ `fastapi-developer`, `nextjs-developer`, `code-reviewer`; `guardiao-do-acesso` criado nesta data (teste de resposta abaixo) |
| 4 | `make db-test` verde antes | ✅ depois do ajuste da SPEC: o único vermelho era header de documento (exceções sobrando na SPEC e nomes nus no arquivo novo), corrigido; `=== SUÍTE COMPLETA OK` |

**Decisões do owner, 04/10/2026, sobre a divergência:**
- **Ajustar a etapa e seguir.** A SPEC foi à v2.1: §4 e §4.1 descrevem o estado
  real, a §5.2 deixa de existir, e a U2 fica só com colunas, RPCs, o par
  `revoke`+`grant` e o check 9. O insert direto como `authenticated` vira
  **regressão** no gate da U2, não prova de trabalho novo.
- **Break-glass (§8.1): SQL de operador.** Nada novo no produto; promover owner
  substituto é procedimento documentado de operador, com `audit_log`. Regra
  prática: dois owners ativos. Medido em produção (agregado): FastPark com
  **2 owners** e **1 personnel**.

**Teste do `guardiao-do-acesso`, 04/10: ❌ não responde** — `Agent type
'guardiao-do-acesso' not found`. O arquivo existe em `.claude/agents/`, mas os
agentes são carregados no início da sessão. **A revisão de qualquer sprint espera
o agente responder** depois de recarregar a sessão; a U1 é despachada antes porque
usa só o `fastapi-developer`, e nenhum gate é dado por cumprido sem o guardião.

**Reteste do `guardiao-do-acesso`, nova sessão: ✅ responde** — rodou o `ls` e
reportou as 10 verificações e os itens fixos.

Ainda abertas, perguntar quando a sprint precisar: §8.2 (`app.contact` ×
`tenant_member`), §8.3 (fechar `can_see_company` na raiz — a SPEC recomenda a
constraint), §8.4 (colaborador acessa o painel?).

---

## U1 — As constraints · ✅ aprovada 04/10 · `fastapi-developer`

Sem ciclo de correção: ou as constraints entram, ou falhou por achado.

**Escopo:** migration nova `usuarios_escopo_constraint` com `escopo_nao_vazio`,
`escopo_unidade_tem_empresa` e o índice único `user_scope_sem_duplicata` com
`coalesce` (SPEC §3.3). Só isso. Nenhuma mudança em `util.can_see_*`.

**Gate:** `scripts/teste_escopo_curinga.sql` com as **seis** linhas da SPEC §3,
papel **fixado em `unit_supervisor`**, fixture declarada (2 unidades, 3 empresas):
1. linha com os dois nulos → recusada pelo banco;
2. linha com `unit_id` e `company_id` nulo → recusada;
3. duplicata → recusada pelo índice;
4. supervisor sem linha → 0 unidades **e 0 empresas**;
5. `unit_id` + `company_id` → 1 unidade e 1 empresa;
6. **positivo:** escopo por empresa continua vendo as unidades daquela empresa.

⛔ **Se a migration não puder ser criada em produção, existe escopo-curinga lá.**
Pare e reporte; **não apague linhas**.

**Entregue e parada por achado, 04/10 (`fastapi-developer`):** migration
`20261004230758_usuarios_escopo_constraint.sql` (as duas checks e o índice com
`coalesce`; o `do $$` confere a forma, não só o nome) e
`scripts/teste_escopo_curinga.sql` (seis linhas, papel conferido como
`unit_supervisor`, recusas por `sqlstate:constraint`; a 3b — só empresa repetida
— só o `coalesce` pega). Vermelho sem a migration, verde com ela; quatro mutações
mortas.

**Produção (agregado, somente leitura): `app.user_scope` tem 0 linhas** — nenhum
escopo-curinga lá, a migration entraria limpa. Consequência registrada: hoje todo
papel fora do atalho (`owner`, `executive`, `hr`, `personnel`) enxerga zero em
produção.

**A parada:** com a migration, a suíte real fica vermelha. Sete gravações de
fixture/seed usam o formato curinga da §3.1: seis "só unidade" (98:103, 98:2773,
87:88, 77:145, 97:2421, `seed.sql:132`) e uma de dois nulos (98:111, o
`accounting` "do tenant inteiro"). As asserções do 98 que leem o escopo de tenant
inteiro do `accounting` (~1131–1137, ~1182) dependem disso. Correção candidata,
provada numa cópia com a suíte inteira verde: preencher `company_id` com a empresa
da própria unidade nas seis, e trocar os dois nulos por `company_id` = a única
empresa do tenant A no 98 — nenhum valor afirmado muda. Levado ao dono (fixture
do 98 e do seed).

**Decisão do dono, 04/10/2026: corrigir as fixtures e o seed** como a correção
candidata — empresa da própria unidade nas seis linhas "só unidade"; a única
empresa do tenant A no lugar dos dois nulos do `accounting`. São linhas de
fixture, não asserção: nenhum valor afirmado muda. Devolvido ao desenvolvedor.

**Correção aplicada, 04/10:** as sete linhas (98:103, 98:111, 98:2773, 87:88,
77:145, 97:2421, `seed.sql:132`) e o comentário do `accounting` no 98. O diff do
98 tem quatro trechos (três inserts e o comentário), nenhuma asserção; a linha
1160 passa sem mudança. Seed provado num banco descartável com as 74 migrations,
em transação desfeita: o novo entra limpo, o do HEAD é recusado por
`escopo_unidade_tem_empresa`. ⚠️ O banco de dev local (55322, 48 de 74 no ledger)
tem a linha antiga do seed e vai falhar ao receber a migration — `db reset` ou
`update` da linha antes; decisão do dono, não feito.

**Conferido pelo orquestrador na árvore real, 04/10:** `=== SUÍTE COMPLETA OK`
(com `ESCOPO CURINGA OK`), diff do 98 com 4 trechos, pytest 1678. Revisão
despachada.

**`guardiao-do-acesso`, 04/10 — APROVADO.** Suíte verde em banco próprio.
1–4 PASSA com fixture própria (1 tenant, 3 empresas, 2 unidades, papel conferido
`unit_supervisor`): dois nulos e unidade sem empresa recusados; escopo só por
empresa vê a unidade dela e não a outra; sem linha, zero e zero. Mutação: sem as
CHECKs, uma linha só com unidade faz o supervisor ver as 3 empresas. 5 e 6 PASSA
como `authenticated` com claims de `owner` (`permission denied for table` em
insert, update e delete; controle: o owner lê o próprio tenant). 7–10 PENDENTE
(U2). Itens fixos PASSA: 98 só fixture, 99 intacto, nenhuma migration aplicada
mexida, nada em `util.can_see_*`, nenhuma linha de escopo apagada. Produção,
agregado: 0 linhas, 0 violações, constraints ainda ausentes.

**`code-reviewer`, 04/10 — APROVADO.** Suíte em banco próprio, pytest 1678,
lint limpo (Vitest teve timeouts com a suíte de banco e o guardião rodando em
paralelo; o arquivo sozinho passa — instabilidade de carga, sem mudança em
`frontend/`). Cinco mutações mortas (cada check, o índice, o índice sem
`coalesce`, os três). A migration falha alto com linha curinga, duplicata ou
índice homônimo sem `coalesce`. A correção de fixtures não enfraquece nada: o
tenant A tem uma empresa só, então o `accounting` por empresa equivale ao tenant
inteiro, e agora exercita o ramo `company_id = u.company_id`.
- **MÉDIO → condição de aceite da U2:** `escopo_unidade_tem_empresa` exige empresa
  não nula, não a empresa **da** unidade. Medido: (E2, B1 de E1) é aceito e o
  supervisor vê a razão social de E2. Ninguém escreve em `user_scope` hoje, então
  quem fecha é a RPC de escopo (e o convite): validar `unit.company_id =
  company_id` no tenant, com negativo para o par trocado. A alternativa (FK
  composta) é mudança de schema e fica com o dono.
- BAIXO → U2: a conferência do índice no `do $$` usa `like`; somar
  `indnatts = 4`.
- BAIXO → U2: os rótulos "tenant inteiro" do 98 dependem de A ter uma empresa só;
  somar uma asserção de fixture `count = 1`.

**Fechamento da U1, 04/10:** ✅ aprovada. Não commitada, nada em produção.

## U2 — As RPCs · ✅ aprovada 05/10 (ciclo 1/2) · `fastapi-developer`

**Escopo:** `usuarios_colunas_da_lista` (`invited_by`, `deactivated_at`) e
`usuarios_rpc` com as quatro funções (`fn_convidar_usuario`, `fn_definir_papel`,
`fn_definir_escopo`, `fn_desativar_membro`), todas `security definer`,
`search_path = ''`, com `p_tenant_id`, recusas `P0001`, `audit_log` com
`action = 'update'`, e o **par** `revoke … from public, anon` + `grant … to
authenticated, service_role` por função. ~~Estender o check 9~~ — ele já varre
`public` desde 07/09 (ver a entrega).

⛔ Parada: quatro funções novas em `public` (autorizada pela etapa).

**Gate — quatro negativos, três positivos:**
- insert direto em `app.tenant_member` como `authenticated` com um `owner` →
  recusado (**regressão**: já vale desde a P1.2b);
- `has_function_privilege('anon', …)` falso para as quatro;
- `fn_definir_papel` por `hr` → `not_owner`;
- `fn_definir_escopo` por `unit_supervisor` → `not_admin`, e o escopo não mudou;
- **positivo:** `owner` define papel → papel gravado e `audit_log` com `antes` e
  `depois` não nulos, `action = 'update'` (não alargar o CHECK);
- **positivo:** desativar → `active = false`, linha preservada, `deactivated_at`;
- **positivo:** escopo vazio → `escopo_vazio` e as linhas anteriores continuam
  (contar antes e depois).
Também gate desta sprint: `ultimo_owner` e `e_voce_mesmo`.
**Condições herdadas da revisão da U1:** `fn_definir_escopo` e
`fn_convidar_usuario` recusam unidade cuja empresa não é a `company_id` da linha
(recusa nomeada, ex. `unidade_fora_da_empresa`), com negativo para o par trocado
e positivo para o par certo; o `do $$` da `usuarios_escopo_constraint` passa a
conferir `indnatts = 4` (a migration nunca foi aplicada, pode ser editada no
lugar); o 98 ganha a asserção de fixture "tenant A tem uma empresa" junto do
insert do `accounting`.

**Entregue, 05/10 (`fastapi-developer`), sem parada:** migrations
`20261005011136_usuarios_colunas_da_lista` (`invited_by`, `deactivated_at`) e
`20261005011138_usuarios_rpc` (as quatro funções + helper
`util.parse_user_scope`, invoker e sem grant). `p_scope` = lista não vazia de
`{company_id, unit_id?}`; "todas as unidades" = uma entrada por empresa.
Recusas, na ordem:
- convite: `not_admin`, `ja_e_membro`, `escopo_vazio`, `escopo_sem_empresa`,
  `empresa_fora_do_tenant`, `unidade_fora_da_empresa`;
- papel: `not_owner`, `member_not_found`, `ultimo_owner`;
- escopo: `not_admin`, `member_not_found`, `escopo_vazio`, `escopo_sem_empresa`,
  `empresa_fora_do_tenant`, `unidade_fora_da_empresa`;
- desativar: `not_admin`, `e_voce_mesmo`, `member_not_found` (acrescentada),
  `ultimo_owner`.
Auditoria: convite `insert`, as outras `update` (CHECK intacto, sem policy
nova); chamada sem efeito não grava. Lock `for no key update` em `app.tenant`
antes de tudo, com o papel relido depois: `scripts/teste_usuarios_concorrencia.py`
(duas sessões) prova que dois owners se rebaixando terminam com um owner. Gate
em `scripts/teste_usuarios_rpc.sql`. 30 mutações mortas. Condições da U1:
`indnatts = 4` e a asserção "tenant A tem uma empresa" no 98.
**O check 9 do 99 já varria `public` desde 07/09** — a premissa da SPEC estava
velha; nenhum diff no 99, e o check pega `grant` a `anon` numa das quatro
(provado num clone). SPEC corrigida pelo orquestrador.
Pontos levantados: `hr`/`personnel` podem desativar um `owner` quando há dois
(como a SPEC escreve); convite de `user_id` inexistente em `auth.users` cai na
FK (`23503`), sem recusa nomeada.

**Conferido pelo orquestrador na árvore real, 05/10** (depois de tirar o header
vencido deste arquivo): `=== SUÍTE COMPLETA OK` com `RPCS DE USUÁRIO OK`,
`CORRIDA DE OWNERS` e `ESCOPO CURINGA OK`; 99 sem diff; pytest 1678; ruff limpo.
Revisão despachada.

**`guardiao-do-acesso`, 05/10 — APROVADO, as dez verificações.** Fixture própria
(tenant T com 3 empresas e 2 unidades, tenant X, sete usuários de papéis
distintos). 1–4 regressão da U1 PASSA; 5 e 6 `permission denied for table` em
insert, update e delete como owner autenticado; 7 `anon` e PUBLIC sem EXECUTE
nas quatro, `util.parse_user_scope` sem EXECUTE para ninguém; 8 `not_owner` (hr,
e owner de outro tenant) e `not_admin` com escopo e auditoria inalterados; par
trocado → `unidade_fora_da_empresa`, outro tenant → `empresa_fora_do_tenant`; 9
papel gravado com `audit_log` `update`, autor e antes/depois; `ultimo_owner`; 10
`active = false`, linha preservada, data que não muda na segunda chamada;
`e_voce_mesmo`; convite cria `viewer` com `invited_by` e recusa `ja_e_membro`.
99 intacto e reprova `grant` a `anon`/PUBLIC num clone. CHECK e policy de
`audit_log` intactos. Varredura de senha e token PENDENTE (U3). Leitura de
produção barrada — não necessária nesta sprint.

**`code-reviewer`, 05/10 — APROVADO.** Suíte em banco próprio, pytest 1678,
Vitest 1342, lint limpos. Os sete itens do gate, `ultimo_owner`, `e_voce_mesmo`,
`indnatts = 4` (quinta coluna e `include` reprovam) e a condição da U1 passam.
Mutações mortas: sem `revoke` (pela migration, pelo teste e pelo check 9), sem
`ultimo_owner` nas duas funções, sem o lock (pela corrida), `delete` no lugar de
`active = false`, par trocado aceito. O lock `for no key update` não trava inserts
com FK para `app.tenant` (medido: 0,02 s); só `UPDATE app.tenant` espera, e
ninguém faz isso fora de migration e teste. `util.parse_user_scope` sem grant
não abre caminho. A ordem das recusas não vaza entre tenants.
- **MÉDIO:** o parser de escopo ignora chave desconhecida e trata `unit_id: ""`
  como ausente — `{"company_id": E1, "unitId": U1}` grava a empresa inteira, em
  silêncio. A RPC é chamável pelo PostgREST, então quem fecha é ela.
- **MÉDIO (decisão do dono):** não há caminho para reativar, e `hr`/`personnel`
  desativam `owner` quando há dois — juntos, tiram um owner de forma
  irreversível pelo produto.
- BAIXOS: o convite grava `action = 'insert'` (no CHECK; a SPEC dizia `update`);
  o lock vem antes da autorização (qualquer `authenticated` segura a linha de um
  tenant alheio por uma transação); `invited_by` sem `on delete` (apagar no Auth
  quem convidou falha); `23503` diz se um uuid existe em `auth.users`.

**Decisões do dono, 05/10/2026:**
- **Só `owner` desativa `owner`.** Recusa nova nomeada em `fn_desativar_membro`.
- **Reativar é procedimento de operador** (SQL com `audit_log`, como o
  break-glass). Nada novo no produto; a tela avisa que desativar é definitivo.

**Ciclo 1/2 despachado em 05/10:** a recusa `owner_so_por_owner`, o parser
estrito (`escopo_invalido` para chave fora de `{company_id, unit_id}` e para
`unit_id` vazio), a checagem de pertencer ao tenant antes do lock, e a SPEC
alinhada (convite `insert`, `invited_by` sem `on delete` por preservar a
autoria).

**Ciclo 1 entregue, 05/10:** `owner_so_por_owner` em `fn_desativar_membro`;
parser estrito (`escopo_invalido` para entrada que não é objeto, chave fora de
`{company_id, unit_id}`, tipo não-string, `null` JSON e string vazia; sem
`nullif`); `util.has_tenant` antes do lock nas quatro, papel relido depois. Gate
com 14 negativos de `escopo_invalido` (sete casos × duas funções), bloco
`owner_so_por_owner` com positivo (owner desativa owner), e o intruso de outro
tenant recebendo a recusa sem esperar a linha travada. Mutações mortas, inclusive
as 30 do ciclo anterior.
**Guarda morta, mantida de propósito:** com `owner_so_por_owner`, `ultimo_owner`
em `fn_desativar_membro` não dispara — quem desativa owner é owner ativo e não é
o alvo, então sobram dois. A mutação que a remove sobrevive por isso. Fica como
defesa (se o atalho de papel mudar), decisão do orquestrador; em
`fn_definir_papel` ela é alcançável e testada.

**Conferido pelo orquestrador na árvore real, 05/10:** `=== SUÍTE COMPLETA OK`
com `RPCS DE USUÁRIO OK` e `CORRIDA DE OWNERS`; pytest 1678. Re-revisão
despachada.

**`guardiao-do-acesso`, ciclo 1 — APROVADO.** Fixture própria (dois tenants,
dois owners, hr, personnel, três supervisores, um viewer). As dez verificações
PASSA. (a) `hr` e `personnel` desativando owner → `owner_so_por_owner`, dois
owners seguem ativos, sem auditoria; owner desativa owner passa; o owner que
sobra recebe `ultimo_owner` ao se rebaixar. (b) 14 de 14 `escopo_invalido`
(sete casos × duas funções), nada gravado; formas válidas passam. (c) duas
sessões, `lock_timeout` 700 ms: o owner de outro tenant recebe a recusa em
3–6 ms nas quatro; o owner do próprio tenant, como controle, espera e dá `55P03`.
Itens fixos PASSA. Varredura de senha e token PENDENTE (U3). Observação
registrada: um membro do próprio tenant sem papel de admin ainda passa pelo
`has_tenant` e segura a linha até a recusa por papel — dentro do tenant, fora do
pedido do ciclo.

**`code-reviewer`, ciclo 1 — APROVADO.** Suíte em banco próprio, pytest 1678,
lint limpos. MÉDIO do parser fechado (sonda própria: `unitId`, `unit_id: ""`,
`Company_ID`, booleano, array aninhado, válida junto de inválida → todas
`escopo_invalido`, nada gravado). `owner_so_por_owner` com negativos (hr,
personnel; viewer, owner de outro tenant e owner inativo dão `not_admin`) e
positivo. `has_tenant` antes do lock não reabre a corrida (papel relido com
`active`). As duas expectativas trocadas no teste são consequência da regra —
sem `owner_so_por_owner` elas mesmas reprovam. A guarda `ultimo_owner` mantida
só dispara se um escritor fora das RPCs desativar o chamador entre a releitura e
a contagem — é a defesa certa. 11 mutações mortas. BAIXOS: desativar owner já
inativo devolve ok sem gravar (o `return` vem antes de `owner_so_por_owner`); a
tabela de recusas da SPEC estava atrás — **alinhada pelo orquestrador**; a
mutação que remove a guarda mantida sobrevive (decisão registrada).

**Fechamento da U2, 05/10:** ✅ aprovada (ciclo 1/2). Não commitada, nada em
produção.

## U3 — Convite e lista · ✅ aprovada no ciclo 2/2 · `fastapi-developer` + `nextjs-developer`

**Escopo:** FastAPI → Admin API do Supabase (convite, devolve `user_id`) →
`fn_convidar_usuario`. `ja_e_membro` checado **antes** do Admin API. Rota
`GET /usuarios` lendo `auth.users` com `service_role` e revalidando papel. Tela de
lista e convite; seletor de escopo sem estado vazio e unidade sempre com a
empresa; sem campo de senha; ação "reenviar convite".

**Gate:** convidado chega como `viewer`; a lista mostra **nome, e-mail e quem
convidou** do recém-convidado; o seletor não submete vazio nem unidade sem
empresa; nenhuma resposta de API contém senha ou token de convite (varredura de
JSON).

**Backend entregue, 05/10 (`fastapi-developer`), sem parada:**
`backend/server/routers/usuarios.py`, `backend/operax/core/auth_admin.py`,
`backend/tests/test_usuarios.py` (74), `scripts/teste_usuarios_rota.py` (35).
- `POST /usuarios/convites` `{email, scope}` (fechado; `unit_id: null` explícito
  → 422): papel → vínculo neste tenant (`ja_e_membro` 409, **sem** chamar o Admin
  API) → escopo validado pelo mesmo `util.parse_user_scope` (antes do e-mail) →
  Admin API só para e-mail novo → `fn_convidar_usuario` como o usuário. 201
  `{user_id, email, role: "viewer", invitation_sent}`; 502 `convite_nao_enviado`.
- `POST /usuarios/{id}/reenviar-convite` `{}`: 404 `member_not_found`, 409
  `membro_inativo` e `convite_ja_aceito` (não é "resetar senha").
- `GET /usuarios`: nome, e-mail, papel, ativo, `invited_by` com nome e e-mail,
  `scope_mode` `by_role` (com `scope: []`) para `owner/executive/hr/personnel`,
  conferido por teste contra `util.can_see_*`.
- E-mail que já tem conta no Auth: reusa a identidade, nenhum e-mail sai,
  `invitation_sent: false`. RPC recusando depois do Admin API (só por corrida):
  a identidade fica no Auth sem vínculo e é reusada no próximo convite — não se
  apaga, porque o `cascade` levaria o vínculo de outro tenant.
- `redirectTo` = `{dashboard_url}/convite` (variável que já existia); a página
  `/convite` ainda não existe, e a URL precisa estar nas Redirect URLs do Auth.
- Varredura: GoTrue falso devolvendo os sete campos proibidos preenchidos; nenhum
  aparece em resposta, log ou exceção, em dez cenários.
- Mutações mortas, inclusive `ja_e_membro` depois do Admin API, `action_link`
  vazando no `detail`, e o filtro de tenant da lista trocado por tautologia.
Não verificado contra o GoTrue real: a premissa de que `/invite` reenvia para
usuário não confirmado; dois convites simultâneos do mesmo e-mail novo.

**Decisões do dono, 05/10/2026:**
- **O convite pede nome**, obrigatório, enviado ao Auth nos metadados — fecha o
  gate "a lista mostra o nome do recém-convidado".
- **`invitation_sent: false` fica**, e a tela explica ("essa pessoa já tem
  conta; o acesso foi liberado sem novo e-mail").

**Nome entregue, 05/10:** `POST /usuarios/convites` = `{name, email, scope}`
(`name` obrigatório, `strip`, 1–120); vai ao GoTrue em `data.name`. Conta já
existente: o `name` é validado e descartado — os metadados de quem já existe não
são reescritos. O reenvio não manda `data`. O gate do nome deixou de ser
simulado: o GoTrue falso grava os metadados do `data` recebido e a lista real
devolve o nome. Mutações do nome e as anteriores mortas.

**Conferido pelo orquestrador na árvore real, 05/10:** `=== SUÍTE COMPLETA OK`
com `ROTAS DE USUÁRIO (U3)`, pytest 1760, ruff limpo. Tela despachada ao
`nextjs-developer`. O frontend só tem `/login`: a página `/convite`, onde o
convidado define a PRÓPRIA senha pelo SDK do Supabase, entra nesta trilha. Ela
não contradiz a §5.6 (que proíbe o admin tocar senha): é a decisão 2 da §2.

**Frontend entregue, 05/10 (`nextjs-developer`):** `/dashboard/usuarios` (lista
e convite; `notFound()` fora de `owner/hr/personnel`; item "Usuários" no menu) e
`/convite`. Lista: `by_role` mostra só "todas as unidades (pelo papel)", inativo
em cinza com a data, "convite pendente" com reenvio em dois cliques, nenhum
uuid. Formulário: nome e e-mail, sem papel nem senha; o seletor guarda o id da
unidade e tira a empresa da própria linha de `vw_unit` (não há como montar par
trocado); empresa inteira omite `unit_id`; aviso de empresa nova sempre visível.
`/convite`: o cliente do `@supabase/ssr` força PKCE e recusa `#access_token`,
então a página usa um cliente próprio (`detectSessionInUrl: false`), limpa a URL
e trata erro → `#access_token` (`setSession`) → `?code=` → `?token_hash=`
(`verifyOtp invite`) → sessão existente; senha 8–72, `updateUser`, nada em
`lib/api`, log ou `localStorage`. `proxy.ts` deixa só `/convite` passar. 15
mutações mortas; varredura de `password`/`token`/`action_link`/`access_token`
na lista, no convite, no reenvio e nos tokens do link. Empresa sem unidade ativa
não aparece no seletor (não há view de empresa no Caminho 1).

**Conferido pelo orquestrador, 05/10:** Vitest 1418/1418, prettier e tsc limpos.

**Achado do desenvolvedor — convite travado:** quem abre o link e fecha a aba
sem definir senha fica com `email_confirmed_at` gravado; o reenvio dá
`convite_ja_aceito` e o login não tem recuperação.
**Decisão do dono, 05/10/2026: "Esqueci minha senha" no login**, pelo fluxo de
recuperação do Supabase, caindo na mesma página de definir senha. A própria
pessoa sobre a própria conta — nenhum admin toca senha. Devolvido ao
desenvolvedor antes da revisão.

**"Esqueci minha senha" entregue, 05/10:** estado `/login?esqueci` (sem rota nova,
`proxy.ts` inalterado); `resetPasswordForEmail` com `redirectTo` =
`window.location.origin` + `CONVITE_PATH`, pelo cliente do navegador; mensagem
única para sucesso, e-mail inexistente, erro do Auth e de rede; botão desabilitado
durante o envio. `/convite` trata `type=recovery` (`token_hash` → `verifyOtp
recovery`; fragmento → `setSession`), com título e mensagem de link expirado
próprios. `convite_ja_aceito` aponta para "Esqueci minha senha". 7 mutações
mortas. Limitação: redirect de erro do Auth sem `type` cai na mensagem do convite
(não conferido no GoTrue real).

**Conferido pelo orquestrador, 05/10:** Vitest 1432, pytest 1760, prettier e tsc
limpos (suíte de banco já OK depois do backend; a tela não toca banco). Revisão
despachada.

**`guardiao-do-acesso`, 05/10 — APROVADO.** As dez verificações PASSA com fixture
própria. **Varredura de senha e token: PASSA** — app FastAPI inteiro via ASGI
contra o banco real, GoTrue falso devolvendo os sete campos, chaves e valores
procurados em resposta, headers, stdout/stderr, log em DEBUG e traceback, em 201,
200, 409 (três formas de `ja_e_membro`, `convite_ja_aceito`, `membro_inativo`),
404, 422, 403 e 502 (quatro falhas do GoTrue). No front: `type="password"` só em
`/convite` e no login; sem `localStorage`, `sessionStorage` ou `console` nos
arquivos da U3; sem `replaceState` 4 testes falham. Gate da U3: `viewer`, nome,
e-mail e quem convidou na lista, `ja_e_membro` e escopo inválido sem chamar o
Admin API (`auth.users` sem delta). Itens fixos PASSA. PENDENTE: GoTrue real e
Redirect URLs de produção. BAIXO: erro de rede ou timeout no Admin API escapa
como 500 (deveria ser 502 `convite_nao_enviado`); nada vaza hoje, mas os locais
do frame carregam a service key se um dia entrar Sentry com variáveis locais.
Observações: `?code=` da recuperação não traz `type` (título do convite,
cosmético); `?token_hash`/`?code` chegam ao log de acesso da Vercel antes da
limpeza no cliente.

**`code-reviewer`, 05/10 — REPROVADO (um CRÍTICO).** Suíte, pytest 1760, Vitest
1432 e lint verdes. O gate se sustenta nas mutações (`ja_e_membro` antes do
Admin API, escopo antes do e-mail, varredura que pega vazamento real, `by_role`,
filtro de tenant da lista, `/convite` limpando a URL, `proxy` só `/convite`).
- **CRÍTICO:** convidar um e-mail **já ativo em outro tenant** cria um segundo
  vínculo ativo; `resolve_membership` passa a levantar
  `AmbiguousTenantMembershipError` e `deps.py` responde 403 em tudo, `/me`
  inclusive. Provado no banco (`user … is active in 2 tenants`). Qualquer `hr` de
  A tira o acesso de qualquer usuário de B, até o owner, sabendo só o e-mail; B
  não desfaz. O cenário 4 do `teste_usuarios_rota.py` afirmava esse estado. A
  premissa da decisão de 05/10 sobre `invitation_sent: false` ("a pessoa entra
  com a senha que já tem") caiu — Regra 0: a decisão volta ao dono.
- MÉDIO: o reuso não distingue identidade não confirmada (órfão da corrida, convite
  pendente de outro tenant) — nenhum e-mail sai e a tela diz "já tem conta", o
  que é falso.
- MÉDIO: o teste mocka o `createInviteSupabaseClient` inteiro; `detectSessionInUrl:
  true` sobrevive a 560 testes.
- MÉDIO: a recuperação pelo cliente do `@supabase/ssr` é PKCE e volta como
  `?code=` sem `type` — título e mensagem de erro de convite para quem pediu
  recuperação. Marcar o fluxo no `redirectTo`.
- BAIXOS: ordem fragmento→`code` sem guarda; `/convite` sem parâmetro oferece
  troca de senha a qualquer sessão; sem rate limit próprio no convite.

**Decisões do dono, 05/10/2026 (a premissa da decisão anterior caiu):**
- **E-mail ativo em outro cliente → recusa antes do Admin API**, com o código
  `conta_em_outro_cliente` (409). A tela diz que o e-mail já é usado em outro
  cliente e pede outro. Um cliente por usuário continua sendo o modelo; vários
  clientes por usuário fica para etapa própria.
- **Conta sem senha (`email_confirmed_at` nulo) e sem vínculo ativo em cliente
  nenhum → o convite chama o Admin API de novo** (reenvia o e-mail),
  `invitation_sent: true`. "Já tem conta; acesso liberado sem novo e-mail" fica
  só para quem já tem senha e não é ativo em outro cliente.

**Ciclo 1/2 despachado em 05/10:** backend (o CRÍTICO, a conta sem senha, e o
BAIXO do guardião: erro de rede e timeout do Admin API viram 502
`convite_nao_enviado`, sem a chave nos locais do frame) e frontend (mensagem de
`conta_em_outro_cliente`, teste das opções do `createInviteSupabaseClient`, e o
fluxo de recuperação marcado no próprio `redirectTo`).

**Frontend do ciclo 1 entregue, 05/10:** mensagem de `conta_em_outro_cliente`
(sem botão de reenviar); `src/lib/supabase.test.ts` guarda `isSingleton: false`,
`detectSessionInUrl: false` e os mesmos cookies do cliente do painel (a mutação
`detectSessionInUrl: true` agora morre); recuperação com `redirectTo` =
`origin + /convite?fluxo=recuperacao`, lido antes de limpar a URL, com título e
erro de recuperação também no `?code=` PKCE; o BAIXO de `/convite` sem parâmetro
foi feito — sem link, a página mostra "link inválido" mesmo com sessão aberta. 7
mutações mortas. ⚠️ Operação: as Redirect URLs do Auth precisam aceitar
`/convite?fluxo=recuperacao` (um padrão `/convite**` cobre os dois).

**Backend do ciclo 1 entregue, 05/10:** ordem do convite = papel → `ja_e_membro` →
`conta_em_outro_cliente` (409; mesma condição de `_MEMBERSHIP_SQL`: vínculo
ativo, em tenant ativo, diferente deste) → escopo → identidade (nova: Admin API
com `data.name`; existente sem senha e sem vínculo ativo: Admin API de novo, sem
`data`, `invitation_sent: true`; confirmada sem vínculo ativo: reuso,
`invitation_sent: false`) → RPC. Erro de rede (`httpx.HTTPError`) → 502
`convite_nao_enviado`, com a exceção levantada **fora** do `except` (`from None`
não basta: `__context__` carregaria a requisição com a chave); idem no JSON
inválido. Cenário 4 do `teste_usuarios_rota.py` consertado — agora 409 e
`resolve_membership(MEMBER_B)` ainda resolve B —, mais 4b (confirmada com
vínculo só inativo → reuso) e 4c (sem senha e ativa em B → 409). Mutações novas
(C1–C5) e anteriores mortas.

**Conferido pelo orquestrador na árvore real, 05/10:** `=== SUÍTE COMPLETA OK`
com `ROTAS DE USUÁRIO (U3)`, pytest 1776, ruff limpo, Vitest 1438/1438, prettier
e tsc limpos. Re-revisão despachada.

**`guardiao-do-acesso`, ciclo 1 — REPROVADO (o CRÍTICO por outra porta).** Pela
rota, `conta_em_outro_cliente` fecha o bloqueio (409, Admin API não chamado,
`resolve_membership` ainda resolve B, `/me` 200). **Pela RPC direta, não:**
como `authenticated` com claims de um `hr` de A,
`fn_convidar_usuario(A, <user_id ativo em B>, escopo válido)` devolve `ok`, cria
o vínculo, e a pessoa passa a `AmbiguousTenantMembershipError` e 403 no `/me`. A
RPC só confere `ja_e_membro` no próprio tenant (`usuarios_rpc.sql` ~191–204) e é
executável por `authenticated` — basta o uuid. Também deixa uma janela de
corrida na rota entre o `IDENTITY_SQL` e a RPC. Conserto: a RPC recusa
`conta_em_outro_cliente` **sob o lock**, com a mesma condição de
`_MEMBERSHIP_SQL`. O resto PASSA: as dez verificações, a varredura (14 respostas
e o log), o erro de rede (cadeia sem a chave), e os itens fixos.

**`code-reviewer`, ciclo 1 — REPROVADO (dois CRÍTICOS, os dois no banco).** O que
o ciclo prometeu está fechado e provado por mutação (rota, conta sem senha, 502,
os três MÉDIOS do front; a troca do cenário 4 é conserto). Mas a invariante "um
cliente por usuário" só existe na rota:
- **P1:** a RPC direta cria o segundo vínculo ativo (provado com o owner de B:
  `AmbiguousTenantMembershipError`). O uuid não é segredo — está no `sub` de todo
  JWT.
- **P2 (corrida, sem atacante):** A convida um e-mail novo enquanto B vincula o
  mesmo usuário; a checagem da rota roda fora de lock e o lock da RPC é por
  tenant — dois vínculos ativos.
- MÉDIO **P3:** membro ativo de um tenant inativo é reusado em A e fica ambíguo
  quando o tenant volta.
- BAIXO: `conta_em_outro_cliente` revela a existência do e-mail em outro cliente
  (decisão do dono).

**Medido pelo orquestrador:** produção tem 0 usuários ativos em mais de um
tenant. O 98 tem, de propósito, um usuário ativo em dois tenants (`hr` em A,
supervisor em B, ~3371) e o 77 também — um índice único quebraria fixtures que
provam o papel no tenant da linha.

**Decisão do dono, 05/10/2026: recusa na função + trava por usuário**, sem
mudança de schema. A RPC `fn_convidar_usuario` recusa `conta_em_outro_cliente`
sob um `pg_advisory_xact_lock` por `user_id` (serializa A contra B), contando
vínculo ativo em **qualquer** outro tenant, inclusive inativo (fecha o P3).

**Ciclo 2/2 (último) despachado em 05/10.**

**Entregue no ciclo 2/2.** `fn_convidar_usuario` (migration editada no lugar,
nunca aplicada) recusa na ordem `not_admin → ja_e_membro →
pg_advisory_xact_lock(hashtextextended('tenant_member/user/' || user_id, 0)) →
conta_em_outro_cliente → escopo`, contando vínculo `active` em qualquer tenant
≠ `p_tenant_id` sem olhar `app.tenant.active`; o `do $$` exige a sequência e a
condição. A rota alinhou a pré-checagem (sem `t.active`) e mapeia a recusa da
RPC para 409. Uma asserção da U2 em `teste_usuarios_rpc.sql` mudou de sentido
— "convidar em S quem é ativo em T: ok" era o P1 — e o positivo segue em dois
casos (sem vínculo; só inativo em X). Provas: P1 RPC direta, P2 duas sessões
reais (a segunda espera em `advisory` e recebe a recusa; um vínculo só) e pela
rota (5b), P3 tenant suspenso (rpc.sql e rota 4d). Mutações MR1, MR2, MR3, MR3b
e as do ciclo 1 mortas.

**Conferido pelo orquestrador na árvore real, 05/10:** `=== SUÍTE COMPLETA OK`
com `RPCS DE USUÁRIO OK`, `CORRIDA DE OWNERS (U2) E DE TENANTS (U3)` e
`ROTAS DE USUÁRIO (U3)`; pytest 1777, ruff limpo, Vitest 1438/1438, prettier e
tsc limpos. Re-revisão final despachada.

**`code-reviewer`, ciclo 2/2 — APROVADO.** Suíte, pytest 1777, Vitest 1438 e
lint verdes no banco dele. P1 provado com fixture própria (RPC direta como `hr`
de A → `conta_em_outro_cliente`, nenhum vínculo); P2 por mutação própria (sem o
advisory lock, o teste da corrida falha com dois vínculos ativos); P3 por
mutação exigindo `t.active` (morta). Ordem de travas sem ciclo: só o convite
toma a trava por usuário, sempre depois da do tenant, e as outras três RPCs não
criam nem reativam vínculo ativo. A asserção da U2 que mudou de sentido é
conserto. Nenhum item de reprovação automática. Gaps de documentação, corrigidos
pelo orquestrador na SPEC: §5.4 com `conta_em_outro_cliente` e a trava (MÉDIO), e
§8.5 — a reativação por SQL de operador passa por fora da RPC e tem de conferir
vínculo ativo em outro tenant sob a mesma trava (BAIXO). BAIXO aceito: a prova
3b do `do $$` é heurística (regex), coberta pelo teste comportamental.

**`guardiao-do-acesso`, ciclo 2/2 — APROVADO.** Suíte verde no banco dele; as
dez verificações PASSA com papel escrito (1–4 `unit_supervisor`, 5–6 owner
`authenticated` → `permission denied for table`). A, B e C do ciclo 1 fechados
com fixture própria: RPC direta → `conta_em_outro_cliente` e
`resolve_membership` real ainda resolve B; corrida com duas sessões (a segunda em
`advisory`, depois recusada, um vínculo) e, sem o lock, dois vínculos — o teste
discrimina; tenant suspenso recusa. Varredura de senha e token: 18 respostas do
app inteiro com GoTrue falso devolvendo todos os campos secretos, log em DEBUG —
zero achados, e o varredor pega o vazamento de controle. Itens fixos PASSA.
PENDENTE fora do alcance local: GoTrue real e Redirect URLs de produção.

**U3 aprovada em 05/10/2026.**

## U4 — Detalhe e matriz · ✅ aprovada no ciclo 1 · `fastapi-developer` + `nextjs-developer`

**Escopo:** detalhe com papel, escopo, desativar, reenviar convite e a matriz de
domínios em leitura vinda de `app.domain_permission`.

**Gate:** para `hr` o seletor está desabilitado **e a rota recusa**; virar uma
linha de `app.domain_permission` no banco muda a matriz na tela (par fixado
`viewer` → `hr`); os quatro papéis de atalho mostram "todas as unidades (pelo
papel)".

**Premissa do orquestrador, 05/10:** "a rota recusa" e o detalhe com nome e
e-mail (que vivem em `auth.users`) exigem rotas FastAPI — o mesmo padrão de
`GET /usuarios` —, então a U4 tem trilha de backend. Contrato fixado no despacho,
espelho das RPCs da U2, sem mudança de banco: `GET /usuarios/{id}`,
`PUT /usuarios/{id}/papel`, `PUT /usuarios/{id}/escopo`,
`POST /usuarios/{id}/desativar` (todas devolvem `TenantUser`) e
`GET /usuarios/matriz`. Backend e tela correm em paralelo contra o contrato.

**Tela entregue no ciclo 1** (`nextjs-developer`, contra o contrato, sem a API
real): `app/dashboard/usuarios/[userId]` (porta `isAdmin` via `/me`, id não-uuid
→ 404 sem chamar a API), `components/usuarios/user-detail.tsx` e
`scope-picker.tsx` (extraído do convite sem mudar o markup). Seletor de papel só
para owner; matriz do papel **selecionado** vinda de `GET /usuarios/matriz`, com
rótulo como única constante; matriz ausente não vira "nenhum domínio sensível" e
trava o salvar; `by_role` mostra "todas as unidades (pelo papel)" sem ler
`scope`; desativar com confirmação. Vitest 1516/1516, prettier e tsc limpos, 28
mutações mortas. Divergência do despacho, corrigida pelo orquestrador junto ao
backend: os domínios são os cinco valores do enum em inglês (`pii`,
`compensation`, `health`, `disciplinary`, `banking`), não os nomes em português.
Premissas da tela: membro inativo fica só leitura; a tela não esconde de antemão
desativar a si mesmo ou um owner — quem recusa é a API.

**Backend entregue no ciclo 1** (`fastapi-developer`): `GET /usuarios/matriz`
(nove papéis na ordem do enum, `left join` em `app.domain_permission` filtrado
por `allowed` e pelo tenant, papel sem domínio com `[]`; registrada antes de
`/{user_id}`), `GET /usuarios/{id}`, `PUT …/papel` (a **rota** recusa
`not_owner` sem abrir a RPC), `PUT …/escopo`, `POST …/desativar` — todas devolvem
`TenantUser`, relido depois da RPC, com o SQL da lista reaproveitado. Recusa
desconhecida sobe 500, nunca 200; um teste amarra cada tabela de status aos
`raise` da migration. Gate contra banco real em `teste_usuarios_rota.py` §9–13:
hr no papel → 403 e nenhuma auditoria; matriz virada (viewer ganha `pii`, hr
perde `health`) com o tenant vizinho diferente para pegar filtro tautológico;
atalhos `by_role` com `scope: []` mesmo com linha em `user_scope`; outro tenant →
404 nas quatro, sem efeito. Mutações M1–M10, cada uma morta por ao menos uma
camada. Nenhuma migration nova.

**Conferido pelo orquestrador na árvore real, 05/10:** `=== SUÍTE COMPLETA OK`
com `ROTAS DE USUÁRIO (U3 + U4)`; pytest 1859, ruff limpo, Vitest 1516/1516,
prettier e tsc limpos. Contrato front ↔ back conferido rota a rota (caminhos,
métodos, `domains` como lista de valores do enum). Revisão despachada.

**`code-reviewer`, ciclo 1 — APROVADO.** Suíte, pytest 1859, Vitest 1516/1516
(um timeout de 5 s em `conexoes/page.test.tsx`, fora da U4, sob carga paralela;
sozinho passa) e lint verdes. Os três gates provados nas três camadas: rota
recusa `not_owner` sem abrir a RPC (8 papéis), matriz do banco com tenant
vizinho diferente (mutações `sem allowed` e `tenant tautológico` mortas pelo
§9), `by_role` com `scope: []` e tela lendo só `scope_mode`. Nenhuma escrita fora
das RPCs, nenhuma migration nova, detalhe = mesmo `TenantUser` da lista. Três
BAIXO, não bloqueiam: (1) papel ausente da matriz avisa mas não trava o salvar
— só com deriva de enum; (2) o front tipa domínio como `string` para tolerar
domínio novo, mas o backend devolve 500 nesse caso — caminho inalcançável; (3)
a API aceita trocar papel/escopo de membro inativo (premissa da U2; só a tela
deixa em leitura) — decisão futura.

**`guardiao-do-acesso`, ciclo 1 — APROVADO.** Suíte verde no banco dele; as dez
verificações PASSA com papel escrito. Gate da U4 executado pelo app inteiro por
ASGI com `resolve_membership` real: (A) hr → 403 `not_owner`, `audit 0->0`; owner
→ 200 e auditoria com autor; (B) linha virada no banco muda a matriz em A e a de
B fica idêntica, tautologia de tenant reprova; nenhum mapa papel→domínio no
front, só rótulos; (C) os quatro atalhos `by_role` com `scope` vazio mesmo com
linha em `user_scope`, e a tela não exibe a linha injetada; (D) oito chamadas
cruzadas → 404, estado de B idêntico; (E) zero escrita fora das RPCs, com o grep
calibrado contra o 98. Varredura: 38 respostas, iscas em `auth.users` e service
key sentinela, log em DEBUG — zero achados, controle positivo encontrado. Itens
fixos PASSA. Observação BAIXO: a guarda estrutural do `tenant_scope` aceita uma
tautologia que nomeia a coluna fora do placeholder; quem a barra é o teste
comportamental com tenant vizinho diferente, que existe. PENDENTE fora do alcance
local: GoTrue real e Redirect URLs de produção.

**U4 aprovada em 05/10/2026. Etapa de usuários concluída nos gates** — falta o
aceite humano (e-mail, senha, login), que fica fora deles.

---

## Definição de pronto da etapa

`make test && make lint && make db-test` verdes e os quatro gates. Demonstração
automatizável: o `hr` convida com escopo de uma unidade; o membro aparece com
nome, e-mail e quem convidou, como `viewer`, vendo uma unidade e uma empresa; o
`owner` promove a `unit_supervisor` com a matriz ao lado; insert direto como
`authenticated` recusado; `anon` não executa as quatro RPCs; uma linha de
`audit_log` por ação, com autor. Aceite humano (e-mail, senha, login) fica fora
dos gates.
