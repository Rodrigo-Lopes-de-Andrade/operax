// Edge Function da sincronização de batidas — ingestão de /Batidas.
//
// Agendada via pg_cron. Duas passadas, com o mesmo vocabulário que
// `app.detection_run.scope` já usa do lado da detecção (migration 13):
//
//   incremental — a cada 15 min, janela curta (BATIDAS_WINDOW_DAYS, padrão 2)
//   backfill    — 1×/dia, fora de pico, 7 dias (BACKFILL_WINDOW_DAYS)
//
// O backfill existe porque marcação é corrigida depois do fato, e a
// `SPEC-TECNICA.md` contrata que correção na origem até D-7 vire revogação do
// indício já emitido. Enquanto a janela era constante de 2 dias, esse contrato
// era falso por implementação: uma correção feita no quinto dia nunca chegava
// aqui, e qualquer queda que passasse de 48 h deixava um buraco que nenhum
// caminho de código conseguia preencher (§4b, risco 2). Ver
// docs/DECISAO-CADENCIA-SYNC.md.
//
// Invocação manual:
//
//   supabase functions invoke sync-batidas
//   supabase functions invoke sync-batidas --no-verify-jwt --data '{"scope":"backfill"}'
//
// Faz UMA chamada de leitura ao Secullum: GET /Batidas, com janela de data.
// Escopo desta fase: SÓ ingestão ("Batida" + batida_marcacao +
// "BatidaFonteDados"). O motor de detecção não roda aqui.
//
// Resposta: apenas contadores e avisos SEM PII (nomes/e-mails/texto livre nunca
// aparecem — avisos referenciam sempre por id).

import { createSecullumClientFromEnv } from "../_shared/secullum-client.ts";
import { BatidaCorrelationBrokenError, runBatidaSync } from "../_shared/batida-sync.ts";
import {
  createSupabaseBatidaRepositoryFromEnv,
  type SupabaseBatidaRepository,
} from "../_shared/supabase-batida-repository.ts";
import { resolveRunOptions } from "../_shared/run-options.ts";

/** Nome da entidade em `app.sync_run.entity` — o mesmo que `fn_data_freshness` agrupa. */
const ENTITY = "Batida";

async function handleRequest(request: Request): Promise<Response> {
  const { scope, windowDays } = await resolveRunOptions(request);
  const startedAt = new Date().toISOString();
  let repo: SupabaseBatidaRepository | null = null;

  try {
    const secullum = createSecullumClientFromEnv();
    await secullum.login();

    repo = createSupabaseBatidaRepositoryFromEnv();
    const summary = await runBatidaSync(secullum, repo, undefined, undefined, windowDays, scope);

    await repo.recordSyncRun({
      entity: ENTITY,
      scope,
      startedAt,
      finishedAt: new Date().toISOString(),
      status: "completed",
      recordsRead: summary.batidasFetched,
      recordsWritten: summary.batidasUpserted,
      recordsSkipped: summary.batidasSkippedMissingFuncionario,
      error: null,
    });

    return new Response(JSON.stringify({ ok: true, summary }, null, 2), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Erro desconhecido.";
    // A correlação quebrada carrega o resumo do que foi lido e pulado — é o que
    // permite ler "parou" sem abrir o log. Antes ela era um HTTP 200 `{ok:true}`
    // com zero batidas gravadas, e o único sinal era um aviso dentro de um JSON.
    const summary = error instanceof BatidaCorrelationBrokenError ? error.summary : null;
    console.error(`[sync-batidas] Falha na sincronização (${scope}):`, message);

    // A gravação da execução falha aberto: um erro ao registrar não pode
    // esconder o erro que estamos reportando.
    try {
      await repo?.recordSyncRun({
        entity: ENTITY,
        scope,
        startedAt,
        finishedAt: new Date().toISOString(),
        status: "failed",
        recordsRead: summary?.batidasFetched ?? 0,
        recordsWritten: summary?.batidasUpserted ?? 0,
        recordsSkipped: summary?.batidasSkippedMissingFuncionario ?? 0,
        error: message,
      });
    } catch (registro) {
      console.error("[sync-batidas] Falha também ao registrar a execução:", registro);
    }

    return new Response(JSON.stringify({ ok: false, error: message, summary }, null, 2), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

Deno.serve((request) => handleRequest(request));
