# Runbook — as catorze migrations pendentes em produção (21/09/2026)

Produção `nklobmlxyidqxarzisph`, ledger em **64**, última `38_alert_release`.
Captura antes: `supabase/capturas/nklobmlxyidqxarzisph/2026-09-21T1009-antes-agente.sql`
(sem deriva contra a de 17/09).

O classificador do harness barra a montagem dos arquivos de apply mesmo com
autorização ("Protected-Scope IaC Apply"), então **quem aplica é o dono**. O
caminho é o que funcionou para a 36: Management API, `scripts/sb_sql.sh -f`, e o
registro no ledger **na mesma chamada**, dentro de `begin … commit`.

## Ordem (não muda)

1. Captura antes — **feita**.
2. Aplicar as catorze, **nesta ordem**, uma por chamada:

```
20260915200001_ch_telegram_provider.sql
20260915200002_ch_messaging_identity.sql
20260915200003_ch_channel_health.sql
20260915200004_ch_readiness_fn.sql
20260915200005_ch_adhesion_fn.sql
20260917115527_ch_queue_telegram.sql
20260917115529_ch_delivery_by_channel.sql
20260917181556_assistant_prompt_layers.sql
20260917181559_assistant_publish_fn.sql
20260917203425_assistant_metric_scope.sql
20260917203429_assistant_catalog_fn.sql
20260918001032_assistant_run_link.sql
20260920132942_assistant_runs_fn.sql
20260920192201_assistant_test_cost_fn.sql
```

3. Captura depois: `python3 scripts/capturar_producao.py nklobmlxyidqxarzisph --rotulo depois-agente`, e o diff contra a de antes tem de ser **só** o que as catorze criam.
4. Ledger em **78**.

## O comando, por arquivo

Para cada `F` da lista acima (`V` = os 14 dígitos antes do primeiro `_`, `N` = o resto sem `.sql`):

```bash
{ echo 'begin;'; cat "supabase/migrations/$F"; \
  echo "insert into supabase_migrations.schema_migrations (version, name) values ('$V', '$N');"; \
  echo 'commit;'; } > /tmp/apply.sql
scripts/sb_sql.sh nklobmlxyidqxarzisph -f /tmp/apply.sql
```

Cada migration termina num `do $$` que falha alto; se uma falhar, o `begin/commit`
desfaz a migration **e** o registro, e a próxima não deve ser aplicada antes de
entender o porquê.

Ou, as catorze de uma vez, parando na primeira que falhar:

```bash
for F in $(ls supabase/migrations | grep -E '^2026091[5-9]|^2026092'); do
  V=${F%%_*}; N=${F#*_}; N=${N%.sql}
  { echo 'begin;'; cat "supabase/migrations/$F"; \
    echo "insert into supabase_migrations.schema_migrations (version, name) values ('$V', '$N');"; \
    echo 'commit;'; } > /tmp/apply.sql
  echo "== $F"; scripts/sb_sql.sh nklobmlxyidqxarzisph -f /tmp/apply.sql || break
done
```

(O `grep` pega exatamente as catorze: são as únicas com timestamp a partir de 15/09.)

## Depois delas, nesta ordem

- `OPENAI_API_KEY` no serviço `operax-api` do Railway — a v1 semeada pede
  `openai/gpt-5.4-mini`; sem a chave o assistente responde 503.
- Push de `88b7c4d..e9a1f83` (sete commits) — o Railway sobe a API que lê as
  tabelas novas.
- `vercel promote` — o painel com as abas novas e com `GET /canais/telegram/vinculos/{id}`
  na ficha do colaborador, que sem `app.messaging_identity` seria 500.
