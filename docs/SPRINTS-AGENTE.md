<!-- verificar-docs: inexistentes-de-proposito app.assistant_prompt_version app.assistant_prompt_pointer app.assistant_draft app.assistant_draft.frozen_from_version_id app.assistant_metric_scope app.assistant_metric_scope.enabled app.ai_query.prompt_version_id app.ai_query.is_dry_run public.fn_publish_assistant_prompt public.fn_assistant_catalog util.assistant_version_immutable app.work_schedule_day -->
<!-- `app.work_schedule_day` entra na lista porque este documento a CITA para
     contar o erro que ela causou na etapa DP. Ela nunca existiu — ver
     `SPEC-DP.md` §0-bis, que registra as três camadas que existem de verdade. -->

# OperaX — sprints da tela de configuração do assistente

Sequência de implementação de `SPEC-AGENTE.md`. Quatro sprints. Cada um tem
**gate verificável**: gate que não fecha = sprint que não terminou, mesmo com o
código escrito.

Esta etapa **não bloqueia nem é bloqueada** pela etapa DP. Não toca nenhuma
tabela dela e o único objeto compartilhado é `app.metric`, em leitura.

---

## A0 — Reconferência antes de escrever qualquer linha

Não é sprint; é o portão. A `SPEC-AGENTE.md` foi escrita contra o snapshot de
**15 migrations** deste diretório e o repositório em andamento tem **37**. Foi
exatamente assim que a etapa DP perdeu um sprint com `app.work_schedule_day`.

Quatro perguntas, respondidas contra o repo em andamento:

1. `app.metric` ainda tem `code` como PK e nenhum `tenant_id`?
2. `metric_read` continua `using (active)`, sem filtro de tenant?
3. `app.ai_query` tem as 13 colunas da SPEC §0.3 e nenhum vínculo a config?
4. `backend/operax/agente/catalogo.py` existe e é quem monta o catálogo?

**Qualquer "não" para aqui e volta para a SPEC.** Um "não" na 1 ou na 2 muda a
§3b inteira; na 4, muda a §4.3.

### ✅ Respondido em 05/09/2026 — quatro de quatro, nenhum "não"

Medido contra o repositório em andamento (37 migrations).

| # | Resposta | Onde |
|---|---|---|
| 1 | ✅ **sim** — `code text primary key`, e **nenhum `tenant_id`**. As colunas são `code · title · description · target_view · dimensions · filters · domain · active` | `09_integracoes_auditoria.sql` |
| 2 | ✅ **sim** — `create policy metric_read on app.metric for select to authenticated using (active)`. Sem filtro de tenant, porque o catálogo é da plataforma | idem |
| 3 | ✅ **sim** — treze exatas: `id · tenant_id · user_id · question · metric_code · parameters · rows_returned · latency_ms · input_tokens · output_tokens · refused · refusal_reason · created_at`. **Nenhuma aponta para configuração** | idem |
| 4 | ✅ **sim** — `backend/operax/agente/catalogo.py` existe e é quem monta: `BINDINGS`, `from_rows`, `reachable`, `describe`, `choose`, `build` | — |

📌 **A 3 confirma o enquadramento do briefing:** a FK nova é conserto, não
feature. `output_tokens` já está lá com o comentário sobre margem negativa, e
sem `prompt_version_id` ela não responde à pergunta para a qual foi escrita —
porque o modelo passa a variar por versão.

---

## A1 — Fundação: camadas, ponteiro, rascunho

**Por que primeiro:** tudo depende do modelo de versão. E é o único sprint que
mexe em estrutura de segurança — isolado, é revisável em uma sentada.

- Migrations `assistant_prompt_layers` e `assistant_publish_fn`.
- Semente da camada `platform` v1 com o prompt que hoje vive em código.
  **Transcrever, não reescrever.** Se o texto melhorar no caminho, a primeira
  versão deixa de ser o retrato do que estava no ar, e o histórico começa
  mentindo. Melhoria é a v2, com autor e data.
- `public.fn_publish_assistant_prompt` com as cinco validações e o `for update`
  no rascunho.
- Transcrever as sete verificações da SPEC §3a para
  `tests/db/test_assistant_immutability.sql`.

⛔ **Parada obrigatória antes de aplicar:** três tabelas novas em `app` com
policy de RLS.

**Gate:**

- as sete linhas da tabela da SPEC §3a passam como teste, **incluindo a 7** (o
  cascade de `app.tenant` leva versão e ponteiro e não trava na FK);
- publicar duas vezes o mesmo texto devolve `draft_unchanged` e **não** cria
  versão;
- publicar sem ponteiro de plataforma devolve `platform_layer_missing`;
- um `owner` de outro tenant chamando a RPC recebe `not_admin` — e o teste
  chama **a RPC**, não a policy: a função é `security definer` e não herda RLS,
  então é a única checagem que importa;
- `grant execute` para `authenticated` está **escrito** na migration.
  `trg_lock_down_new_function` não cobre `public`; sem a linha, a RPC nasce
  inacessível e o sintoma é 403 sem nada no log.

## A2 — Capacidades

**Por que separado:** é a única parte que o cliente opera sozinho, e a única com
uma invariante que precisa sobreviver a toda mudança futura (SPEC §4.1).

- Migration `assistant_metric_scope` (ausência = habilitada).
- `public.fn_assistant_catalog` — os três filtros numa resposta.
- `catalogo.py` passa a **chamar a RPC** em vez de montar catálogo por query
  própria.

**Gate — dois testes, e o segundo é o que importa:**

1. desabilitar `payroll_summary` faz o assistente responder "não tenho esse
   dado" para uma pergunta de folha, e **habilitar de volta não concede nada a
   um papel sem `compensation`** — continua recusando, agora por domínio. É a
   invariante da §4.1 virada em teste: a tela só estreita.
2. um teste que **falha se `catalogo.py` montar o catálogo sem a RPC** — busca
   por `from app.metric` / `.from("metric")` no módulo. É a régua única da
   §4.3, e é a defesa contra o defeito que o DeskcommCRM pagou para descobrir:
   tela e runtime com réguas próprias divergem só no caso raro, que é onde
   ninguém olha.

## A3 — Telas: configuração, histórico, teste

- Aba **Configuração**: camada `platform` em leitura, camada do tenant editável,
  contador de caracteres contra o limite.
- ⛔ Quando `frozen_from_version_id` do rascunho ≠ versão apontada, a tela mostra
  **as duas** e diz qual o botão substitui (SPEC §2). Esconder uma é o defeito.
- Aba **Histórico**: versões, autor, data, diff, e voltar (move o ponteiro).
- Aba **Teste**: roda de verdade, grava `is_dry_run = true`.
- ⛔ A aba de teste diz, em texto fixo: *"O teste consulta dados reais, com as
  suas permissões."*
- ⛔ **Nenhum seletor de papel na aba de teste.** "Como ficaria para um
  supervisor" se responde listando as métricas que ele alcança — nunca
  executando como ele.

**Gate:** rollback para a v1 com rascunho na v3 mostra as duas versões na tela;
um teste de tela cobra a frase de dados reais e a **ausência** de seletor de
papel — a ausência é testável e some sem aviso se não for.

## A4 — Execuções

- Migration `assistant_run_link` (`prompt_version_id`, `is_dry_run`, índice
  parcial).
- Aba **Execuções**: pergunta, métrica escolhida, linhas, latência, tokens,
  recusa com motivo, versão que produziu.

**Gate:** custo por competência **quebrado por versão de prompt** — é o que as
colunas de token existiam para responder e não respondiam (SPEC §0.3). Dry-run
fora de toda média. Linha anterior ao versionamento aparece como "antes do
versionamento", **nunca** atribuída à v1: atribuir seria inventar procedência,
que é o erro que esta etapa inteira existe para não cometer.

---

## Ordem

```
A0 ── A1 ──┬── A3 ── A4
           │
           └── A2
```

A2 e A3 são paralelos por pessoas diferentes: um é backend + banco, o outro é
tela. A4 depende de A3 só porque a aba mora no mesmo arquivo de abas.

## O que fecha a etapa

Uma mudança de prompt **publicada pelo painel**, em produção, sem deploy — e a
execução seguinte aparecendo em Execuções com a versão nova ao lado. É o ciclo
inteiro num movimento só, e é a única prova de que as quatro partes se
encaixam.

## O que fica fora, com o destrave nomeado

- **Agente autônomo em WhatsApp** (SPEC §6.1) — não é "depois", é outro
  produto, e o caminho para ele passa por derrubar a regra 11 de propósito.
- **Credencial e orçamento por tenant** (§6.2, §6.3) — enquanto a EURECA pagar
  o modelo.
- **Flywheel de propostas** (§6.4) — destrava quando existir rotulagem de
  recusa, nem que seja manual e de 200 linhas.
- **Papel de plataforma** (§1) — a camada `platform` é semeada por migration.
