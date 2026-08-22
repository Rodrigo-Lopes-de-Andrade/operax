// Edge Function da sincronização de batidas — ingestão de /Batidas
// (antecipação consciente da Sprint 2, ver
// supabase/migrations/20260813163000_batidas.sql e
// docs/adr/ADR-007-granularidade-batidas.md). Agendada via Cron Trigger
// (pg_cron, a cada SYNC_BATIDAS_INTERVAL_MINUTES — ver
// supabase/migrations/<a criar>_sync_batidas_cron.sql, ADR-003), mas também
// pode ser invocada manualmente:
//
//   supabase functions invoke sync-batidas
//
// ou, servindo localmente (exige Docker Desktop):
//   supabase functions serve sync-batidas --env-file .env --no-verify-jwt
//   curl -s -X POST http://127.0.0.1:54321/functions/v1/sync-batidas
//
// Faz UMA chamada de leitura ao Secullum: GET /Batidas, com janela deslizante
// FIXA (hoje - 2 dias .. hoje — ver BATIDAS_WINDOW_DAYS em batida-sync.ts).
// Escopo desta fase: SÓ ingestão ("Batida" + batida_marcacao +
// "BatidaFonteDados"). O motor de detecção de desvio (comparação x
// "HorarioDia", geração de `desvio`) NÃO é implementado aqui — continua
// sendo Sprint 2.
//
// Resposta: apenas contadores e avisos SEM PII (nomes/e-mails/texto livre
// nunca aparecem — avisos referenciam sempre por id, nunca por Nome/
// Observacoes, ver docs/06-seguranca-lgpd.md).

import { createSecullumClientFromEnv } from "../_shared/secullum-client.ts";
import { runBatidaSync } from "../_shared/batida-sync.ts";
import { createSupabaseBatidaRepositoryFromEnv } from "../_shared/supabase-batida-repository.ts";

async function handleRequest(): Promise<Response> {
  try {
    const secullum = createSecullumClientFromEnv();
    await secullum.login();

    const repo = createSupabaseBatidaRepositoryFromEnv();
    const summary = await runBatidaSync(secullum, repo);

    return new Response(JSON.stringify({ ok: true, summary }, null, 2), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Erro desconhecido.";
    console.error("[sync-batidas] Falha na sincronização de batidas:", message);
    return new Response(JSON.stringify({ ok: false, error: message }, null, 2), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

Deno.serve(() => handleRequest());
