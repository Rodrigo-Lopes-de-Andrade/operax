# OperaX — Plano de banco por sprint

Cliente âncora: **Kastro Park**. Produto: plataforma de gestão de ponto, pessoas e
custo de pessoal sobre o Secullum, projetada desde o início para ser
comercializada multi-tenant.

Este documento é a instrução de execução para o Claude Code. As migrations já
estão escritas e testadas em Postgres 16 local; o trabalho é aplicá-las com
segurança no projeto real e ajustar o worker no mesmo passo.

---

## Regra de ouro da arquitetura

```
secullum   espelho literal do Secullum (PascalCase). PII completa.
           NUNCA exposto ao PostgREST. Só service_role / conexão direta.

app        modelo de domínio OperaX (snake_case). RLS obrigatória.
           NUNCA exposto ao PostgREST. Alcançado só via view/RPC.

util       helpers SECURITY DEFINER das policies. Sem EXECUTE para anon.

public     ÚNICO schema exposto. Só view (security_invoker = on) e função.
           Nenhuma tabela — há event trigger que impede a criação.
```

**Por que isso importa mais do que RLS:** a anon key vive no bundle do painel.
Qualquer pessoa chama o PostgREST direto, sem passar pelo frontend. "Não fazer
`select *` em Funcionario" é convenção de código, não controle de segurança.
Tabela fora do schema exposto é topologia — erro de policy deixa de ser
vazamento de RG, endereço e filiação.

**Convenção de nomes:** PascalCase entre aspas = campo do Secullum (só em
`secullum`). snake_case = nosso (em `app`, `util`, `public`). O espelho mantém a
grafia original de propósito, para diff contra a origem ser trivial; tudo que é
nosso é minúsculo, que é o que ferramenta, ORM e assistente esperam.

---

## Ordem de execução

| # | Migration | O que faz | Bloqueia |
|---|-----------|-----------|----------|
| 00 | `blindagem_imediata` | revoke anon/authenticated + RLS nas tabelas PascalCase | — |
| 01 | `fundacao_schemas` | cria `secullum`/`app`/`util`, política de privilégio, event trigger | 00 |
| 02 | `tenancy_rls` | tenant, papéis, escopo, matriz de sensibilidade, helpers | 01 |
| 03 | `isolar_secullum` | move PascalCase → `secullum`, resto de public → `app`, `tenant_id` | 02 |
| 04 | `organizacao_colaborador` | empresa, unidade, mapa Secullum, colaborador, PII apartada | 03 |
| 05 | `ponto_desvio` | jornada_dia, deviation_event, ciclo, modo sombra | 04 |
| 06 | `alertas` | regras, outbox, log, guardrail individual×grupo | 05 |
| 07 | `folha_custos` | competência, folha_evento, encargos (Fase 3) | 04 |
| 08 | `documentos_saude_acordos` | documentos, ASO, acordos financeiros (Fases 3–4) | 07 |
| 09 | `integracoes_auditoria` | Vault, sync, importação, audit_log, camada semântica | 08 |
| 10 | `views_publicas` | superfície da API: views + RPCs | 09 |
| 11 | `performance` | índices de FK e RLS, matview, trava de EXECUTE | 10 |

Validação: `scripts/98_teste_isolamento_tenant.sql` e `scripts/99_verificacao_rls.sql`.

---

## Convivência com as migrations que já existem

O repositório **não está vazio**. As 14 migrations do OperaX entram depois das de
vocês, não no lugar delas. Três regras:

1. **Nenhuma migration existente é editada.** Migration já aplicada é história —
   editar faz o `supabase db reset` divergir do que está em produção.
2. **Ordem é timestamp.** As do OperaX começam em `20260815100000`. Se a última
   de vocês for mais nova, renomeie os arquivos do OperaX para timestamps
   posteriores **antes** de aplicar. O pré-voo avisa se isso acontecer.
3. **Colisão de nome é bloqueante.** A migration 03 move tudo que sobrar em
   `public` para `app`, e a 04+ cria as tabelas do modelo novo. Se vocês já têm
   uma `company` ou `employee` em `public`, as duas vão querer o mesmo nome —
   decidir antes: renomear a existente ou adaptar a nossa para reaproveitá-la.
   A seção 6 do pré-voo lista exatamente isso.

### Antes de qualquer migration: rodar o pré-voo

```bash
psql "$DATABASE_URL" -f scripts/01_preflight.sql > docs/preflight-$(date +%Y%m%d).txt
```

Read-only. Simula o que as migrations 00 e 03 vão fazer, sem fazer nada, e
responde as quatro perguntas que travam o início:

- A convenção realmente é PascalCase? (seção 3 vazia = não é, e o predicado das
  migrations precisa mudar)
- O que exatamente vai para `app`? (seção 5 — revisar linha a linha)
- Há colisão de nome? (seção 6 — qualquer linha é bloqueante)
- Os 26% de divergência Empresa × Departamento se confirmam? (seção 9)

**O relatório não contém nenhum dado pessoal** — só nome de objeto, tipo e
contagem. É seguro anexar num PR ou numa conversa.

### Testar a fusão de verdade, não um cenário inventado

`scripts/testar_migrations.sh` usa `scripts/_test_stub_supabase.sql`, que é o
**palpite** de como o schema de vocês se parece. Para testar a fusão real:

```bash
pg_dump "$DATABASE_URL" --schema-only --no-owner --no-privileges \
  -n public > scripts/_baseline.sql
```

Com esse arquivo presente, a suíte passa a aplicar o schema real antes das 12
migrations. Aí "as migrations aplicam limpas" deixa de ser uma hipótese.

`--schema-only` é o ponto: estrutura sem uma linha de dado.

---

## Sprint DB-0 — Inventário

**Antes de aplicar qualquer coisa.**

1. Rodar `scripts/01_preflight.sql` e `scripts/00_diagnostico.sql` no projeto
   real e salvar as saídas em `docs/`.
2. Conferir a premissa central: **as tabelas do Secullum realmente usam
   PascalCase?** As migrations 00 e 03 selecionam por `tablename ~ '^[A-Z]'`.
   Se a convenção não bater, ajustar o predicado antes de rodar.
3. Listar o que em `public` é nosso (minúsculo) — vai para `app` na migration 03.
4. Registrar o inventário de colunas com PII (item 6 do diagnóstico). É o que
   guia o preenchimento de `app.employee_pii`.

**Aceite:** diagnóstico commitado e a linha de cada tabela classificada em
"espelho Secullum" ou "nossa".

---

## Sprint DB-1 — Blindagem (aplicar hoje)

Migration 00. Não move nada, não quebra o worker (`service_role` tem grants
próprios e `BYPASSRLS`), e o frontend ainda não existe.

**Aceite:** a própria migration falha se sobrar qualquer tabela PascalCase
legível por `anon`. Rodar o Advisor do Supabase depois e confirmar que sumiram
os alertas de tabela exposta.

---

## Sprint DB-2 — Fundação e tenancy

Migrations 01 e 02.

**Ação manual obrigatória após a 01:** Dashboard → Settings → API → Exposed
schemas deve conter **apenas** `public` e `graphql_public`. Não adicionar `app`
nem `secullum`.

A 02 cria o tenant `kastro-park` e a matriz de sensibilidade. Decisão embutida
que vale revisar com o cliente: gestor regional, supervisor de unidade e gestor
operacional **não** recebem nenhum domínio sensível — veem ocorrência de ponto
da sua unidade, não veem salário, RG nem ASO. Muda por `UPDATE` em
`app.domain_permission`, sem migration.

**Aceite:** `select util.has_tenant(id) from app.tenant` retorna coerente para o
usuário Owner logado.

---

## Sprint DB-3 — Isolamento + ajuste do worker

Migration 03. **Quebra o worker — aplicar junto com o código no mesmo PR.**

O worker passa a apontar para `secullum`:

```python
# backend/operax/core/db.py — conexão direta, mais rápida para upsert em lote
pool_secullum = ConnectionPool(
    DATABASE_URL,
    kwargs={"options": "-c search_path=secullum"},
)
```

Também adicionar `tenant_id` em todo upsert do worker. A coluna tem default para
o tenant da Kastro Park, então nada quebra hoje — mas o default sai quando entrar
o segundo cliente, e o código precisa já estar mandando o valor.

**Aceite:** worker roda um ciclo completo de sincronização sem erro; a migration
falha sozinha se alguma tabela do espelho continuar alcançável.

---

## Sprint DB-4 — Organização e colaborador

Migration 04. Depois de aplicar, existe trabalho de **dados**, não de schema:

1. Cadastrar as unidades reais de estacionamento em `app.unit`.
2. Preencher `app.unit_secullum_map` — o mapeamento Departamento Secullum →
   unidade. **Este é o passo que resolve os 26% de divergência.** Linha sem
   `validated_at` é mapeamento provisório e deve aparecer sinalizada na UI.
3. Popular `app.employee` a partir de `secullum."Funcionario"`, **sempre pelo
   caminho Funcionario→Empresa**, nunca Departamento→Empresa.
4. Popular `app.employee_pii` com o que hoje está em `secullum."Funcionario"`.

**Aceite:** zero colaborador ativo sem `unit_id`; ou, se houver, eles
aparecem numa fila de pendência de mapeamento.

---

## Sprint DB-5 — Motor de desvio

Migration 05. É o coração do produto e onde estão os riscos maiores.

**Materializar `app.expected_workday` antes de detectar qualquer coisa.** Estacionamento
opera em 12x36 e revezamento. "Batida em dia de folga = desvio automático" gera
falso positivo em massa se a escala esperada não estiver correta. Usar `source` e
`confidence`; linha com `confianca < 80` não deve gerar alerta automático.

**Rodar em modo sombra.** `deteccao_execucao.modo = 'sombra'` por 1–2 semanas,
comparando contra a apuração do Secullum. As views só leem `modo = 'producao'`,
então a sombra não contamina nada. Só ligar produção quando a taxa de falso
positivo estiver conhecida e aceita pelo cliente.

**Vocabulário.** No banco e na UI é sempre *desvio* / *indício*. Nunca "hora
extra" como figura legal: o registro oficial é o Secullum, e se o número do
OperaX divergir e um gestor agir em cima, a exposição é do fornecedor. Todo
drill-down termina em "conferir no Secullum".

**Reprocessamento.** Nunca deletar evento — usar `app.revoke_deviation()`. O índice
único parcial (`colaborador, data_ref, tipo` onde ativo e produção) garante que
reprocessar não duplica.

**Dashboard × relatório.** O dashboard filtra por `reference_date` (data do fato). O
relatório agrupa por ciclo. Quando um desvio é detectado tarde, o relatório
precisa declarar "inclui N ocorrências de dias anteriores" — senão os números
parecem divergir e a garantia de consistência cai por terra na percepção do
cliente.

**Aceite:** reprocessar o mesmo período duas vezes não altera a contagem;
`fn_kpi_period` e a soma de `vw_deviation_summary_by_unit` batem exatamente.

---

## Sprint DB-6 — Alertas

Migration 06. Toda regra nasce `ativo = false`. Só ligar depois de homologada com
o cliente e validada pelo jurídico/RH.

**O motor nunca envia.** Ele enfileira em `app.alert_queue`; um sender consome com
`SELECT ... FOR UPDATE SKIP LOCKED`, respeitando `idempotency_key`, com backoff
em `next_attempt_at`. Falha de rede no meio do lote não pode virar alerta
duplicado no WhatsApp do gestor.

**Individual nunca vai para grupo.** Imposto por trigger. Grupo recebe agregado;
o nominal vai para o responsável direto.

Preencher `alerta_enviado.custo_centavos`. Sem isso não há como saber se a
sustentação mensal ficou com margem negativa quando o volume crescer.

---

## Sprint DB-7 a DB-9 — Folha, documentos, integrações

Migrations 07, 08 e 09. **Modelo não validado contra dado real** — estão isolados
justamente para poderem ser reescritos sem tocar no núcleo.

- Folha é **file-first**: `source` aceita planilha e arquivo desde já; API do
  Domínio é só mais uma origem. Se o Domínio não abrir, o produto funciona igual.
- ASO guarda apenas aptidão e validade. Sem diagnóstico, sem CID, sem descrição
  de restrição.
- `acordo_financeiro.documento_id` é NOT NULL: desconto sem autorização
  documentada não se registra.
- Credencial de integração vai para o **Vault**; `app.integration_secret` guarda
  só o ponteiro, e nenhum papel do painel lê essa tabela — nem o owner.
- O assistente de IA usa `app.metric`, um catálogo fechado. Sem text-to-SQL
  livre: com salário e dado de saúde em base multi-tenant, LLM gerando SQL solto
  é vazamento cruzado e resposta errada apresentada com confiança.

---

## Sprint DB-10 e DB-11 — Superfície pública e performance

Migrations 10 e 11.

Toda view usa `security_invoker = on`. Sem isso a view roda com privilégio do
dono e **ignora a RLS das tabelas base** — é o alerta `security_definer_view` do
linter do Supabase e a forma mais comum de vazamento em projeto que "tem RLS".
A migration falha sozinha se alguma view escapar.

`app.mv_deviation_day` é materialized view e **não respeita RLS**: contém todos os
tenants. Por isso nunca é exposta. Quem serve o dashboard a partir dela é a rota
server-side no Vercel, com `service_role` e filtro explícito de tenant e escopo.
O worker chama `app.refresh_dashboard()` ao final de cada execução do motor.

---

## Sprint DB-12 — Verificação

```bash
./scripts/testar_migrations.sh        # banco descartável: stub + 14 migrations + testes
psql "$DATABASE_URL" -f scripts/98_teste_isolamento_tenant.sql
psql "$DATABASE_URL" -f scripts/99_verificacao_rls.sql
```

Rodar de novo **a cada PR que mexer em policy, view ou grant**. São 23 asserções
funcionais (dois tenants, quatro papéis) e 11 verificações estruturais.

---

## Encaixe nas sprints do produto

| Sprint do produto | Estado | Depende de |
|---|---|---|
| 0 — Fundação | ✅ | — |
| 1 — Sincronização cadastral | 🟡 | **DB-3** (worker aponta para `secullum`) |
| 2 — Motor de detecção | ⬜ | **DB-5** — não começar antes; o grão de `deviation_event` define o motor |
| 3 — Relatório consolidado | ⬜ | **DB-6** + motor rodando em sombra com falso positivo conhecido |
| 4 — Dashboard | ⬜ | **DB-10** + migração do front para Vercel |

DB-1 e DB-2 podem entrar em paralelo com a Sprint 1 — não bloqueiam nada.
DB-3 é o único que exige coordenação com código.

---

## Decisões do Owner que já viraram configuração

Não precisam mais de decisão para o schema avançar; são `UPDATE`:

| Decisão pendente | Onde vive agora |
|---|---|
| Direção do desvio contabilizada | `app.deviation_type_config.counts_as_deviation` |
| Tolerância por tipo | `app.deviation_type_config.tolerancia_*_min` |
| Quais alertas disparam | `app.alert_rule.active` + `.gera_alerta` |
| Quem vê salário / RG / ASO | `app.domain_permission` |
| Periodicidade do relatório | `app.alert_rule.cron_window` |
| Gestor com acesso ao painel | `app.tenant_member` + `app.user_scope` (RLS já suporta) |

---

## Riscos abertos

1. **Convenção PascalCase.** As migrations 00 e 03 dependem dela. Confirmar no
   DB-0 antes de aplicar.
2. **Escala 12x36.** Se `Horario`/`HorarioDia` do Secullum não representar a
   escala fielmente, `expected_workday` fica com confiança baixa e o motor não pode
   ligar em produção. Pode exigir cadastro manual de escala.
3. **Domínio.** Integração por API pode simplesmente não ser liberada. O modelo
   file-first cobre, mas a expectativa comercial precisa acompanhar.
4. **Evolution API.** Solução não oficial: risco de banimento de número e sem
   SLA. Planejar migração para a Cloud API oficial antes de escalar volume.
5. **Storage de documentos.** A policy do bucket precisa espelhar
   `util.can_see_employee`. RLS de tabela **não** protege o objeto no Storage.
6. **`audit_log`.** Cresce rápido. Particionar por mês quando passar de ~50M linhas.
