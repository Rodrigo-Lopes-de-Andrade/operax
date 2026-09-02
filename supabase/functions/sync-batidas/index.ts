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
import { createSupabaseBatidaRepositoryFromEnv } from "../_shared/supabase-batida-repository.ts";
import { getSql, type Sql } from "../_shared/postgres-client.ts";
import { claimSyncRun, closeSyncRun } from "../_shared/sync-run.ts";
import { requireSyncSecret } from "../_shared/require-secret.ts";
import { resolveRunOptions } from "../_shared/run-options.ts";

/** Prefixo de log — o mesmo que o resto da função usa. */
const LOG = "[sync-batidas]";

/** Nome da entidade em `app.sync_run.entity` — o mesmo que `fn_data_freshness` agrupa. */
const ENTITY = "Batida";

async function handleRequest(request: Request): Promise<Response> {
  // Antes de tudo, inclusive de ler o corpo: metade do que o segredo protege é
  // a carga que uma invocação não autorizada geraria.
  const recusa = await requireSyncSecret(request, LOG);
  if (recusa) return recusa;

  const { scope, windowDays } = await resolveRunOptions(request);
  let sql: Sql | null = null;
  let runId: string | null = null;

  try {
    // Reivindicar antes de falar com a origem: reivindicar depois protegeria o
    // banco e deixaria o Secullum tomar as duas chamadas. Os dois escopos
    // disputam o MESMO lock (migration 34) porque escrevem as mesmas tabelas —
    // é o que aposenta a heurística do minuto 7 do backfill.
    sql = getSql();
    const claim = await claimSyncRun(sql, LOG, ENTITY, scope);
    if (!claim.ok && claim.reason === "em_andamento") {
      console.warn(`${LOG} já há uma execução em andamento — esta invocação não faz nada.`);
      return new Response(
        JSON.stringify({ ok: false, error: "sincronização já em andamento" }, null, 2),
        { status: 409, headers: { "Content-Type": "application/json" } },
      );
    }
    // `sem_integracao` segue sem diário e sem lock — está logado alto lá dentro.
    runId = claim.ok ? claim.id : null;

    const secullum = createSecullumClientFromEnv();
    await secullum.login();

    const repo = createSupabaseBatidaRepositoryFromEnv();
    const summary = await runBatidaSync(secullum, repo, undefined, undefined, windowDays, scope);

    if (runId) {
      await closeSyncRun(sql, LOG, runId, {
        status: "completed",
        recordsRead: summary.batidasFetched,
        recordsWritten: summary.batidasUpserted,
        recordsSkipped: summary.batidasSkippedMissingFuncionario,
        error: null,
      });
    }

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
    console.error(`${LOG} Falha na sincronização (${scope}):`, message);

    // O fechamento falha aberto: um erro ao registrar não pode esconder o erro
    // que estamos reportando.
    if (sql && runId) {
      try {
        await closeSyncRun(sql, LOG, runId, {
          status: "failed",
          recordsRead: summary?.batidasFetched ?? 0,
          recordsWritten: summary?.batidasUpserted ?? 0,
          recordsSkipped: summary?.batidasSkippedMissingFuncionario ?? 0,
          error: message,
        });
      } catch (registro) {
        console.error(`${LOG} Falha também ao fechar a execução:`, registro);
      }
    }

    return new Response(JSON.stringify({ ok: false, error: message, summary }, null, 2), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

Deno.serve((request) => handleRequest(request));
