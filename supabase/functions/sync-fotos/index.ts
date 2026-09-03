// Edge Function da sincronização de fotos — o 6º endpoint do Secullum.
//
// POR QUE ELA EXISTE, E POR QUE AQUI
// Em 02/09/2026 a outra equipe subiu um job `sync-fotos` na Vercel, com seis
// colunas novas em `secullum."Funcionario"`. Enquanto ele existir falando
// PostgREST, tirar `app`/`secullum` dos exposed schemas derruba a
// sincronização — foi o incidente de 27/08, e é o que mantinha a correção
// bloqueada. Com o job aqui, por conexão direta, a troca de runner fica
// completa: os quatro jobs de `pg_cron` passam a chamar Edge Functions e a
// lista de schemas expostos volta ao que o CLAUDE.md exige.
//
// Invocação:
//   supabase functions invoke sync-fotos
//   ... --data '{"limit": 1}'     # uma foto só, para medir o payload da origem
//
// Faz UMA chamada de leitura por funcionário da fila:
//   GET Funcionarios/fotos?funcionarioId=<Id>
//
// 🔴 A resposta NUNCA carrega imagem: só contadores e avisos, e os avisos
// referenciam funcionário por id. `"Foto"` é a coluna mais restrita do schema.

import { createSecullumClientFromEnv } from "../_shared/secullum-client.ts";
import { FOTOS_BATCH_DEFAULT, runFotoSync } from "../_shared/foto-sync.ts";
import { createSupabaseFotoRepositoryFromEnv } from "../_shared/supabase-foto-repository.ts";
import { getSql, type Sql } from "../_shared/postgres-client.ts";
import { claimSyncRun, closeSyncRun } from "../_shared/sync-run.ts";
import { requireSyncSecret } from "../_shared/require-secret.ts";

const LOG = "[sync-fotos]";

/**
 * Nome da entidade em `app.sync_run.entity`.
 *
 * ⚠️ A cadência dela é DIÁRIA, e `fn_data_freshness` usaria o limiar padrão de
 * 45 min — o que deixaria esta entidade eternamente `is_stale` e, como o painel
 * mostra a entidade mais velha, faria o produto inteiro dizer "atrasado" para
 * sempre. A migration 35 dá a `Foto` o limiar de 36 h, que é 1,5x a cadência,
 * pela mesma regra das outras.
 */
const ENTITY = "Foto";

/**
 * Quantos funcionários por passada.
 *
 * Precedência invocação > ambiente > padrão, a mesma de `resolveRunOptions`. O
 * lote existe porque cada foto é uma chamada à origem: a fila inteira numa
 * passada seria um pico contra o Secullum, e a fila é ordenada justamente para
 * que passadas sucessivas cubram todo mundo sem precisar disso.
 */
async function resolverLimite(request: Request): Promise<number> {
  let pedido: unknown = null;
  try {
    pedido = await request.json();
  } catch {
    pedido = null; // corpo vazio ou inválido cai no padrão, sem derrubar a passada
  }
  const doCorpo = (pedido as { limit?: unknown } | null)?.limit;
  if (typeof doCorpo === "number" && Number.isInteger(doCorpo) && doCorpo > 0) return doCorpo;

  const doAmbiente = Number(Deno.env.get("FOTOS_BATCH") ?? "");
  if (Number.isInteger(doAmbiente) && doAmbiente > 0) return doAmbiente;

  return FOTOS_BATCH_DEFAULT;
}

async function handleRequest(request: Request): Promise<Response> {
  const recusa = await requireSyncSecret(request, LOG);
  if (recusa) return recusa;

  const limit = await resolverLimite(request);
  let sql: Sql | null = null;
  let runId: string | null = null;

  try {
    sql = getSql();
    const claim = await claimSyncRun(sql, LOG, ENTITY, "incremental");
    if (!claim.ok && claim.reason === "em_andamento") {
      console.warn(`${LOG} já há uma execução em andamento — esta invocação não faz nada.`);
      return new Response(
        JSON.stringify({ ok: false, error: "sincronização já em andamento" }, null, 2),
        { status: 409, headers: { "Content-Type": "application/json" } },
      );
    }
    runId = claim.ok ? claim.id : null;

    const secullum = createSecullumClientFromEnv();
    await secullum.login();

    const repo = createSupabaseFotoRepositoryFromEnv();
    const summary = await runFotoSync(secullum, repo, undefined, limit);

    // Uma passada em que TUDO falhou não é sucesso, mesmo com a fila lida. Onde
    // parte passou, `completed` com o número de falhas no `error` diz mais que
    // um veredito binário.
    const houveSucesso = summary.stored + summary.unchanged + summary.absent > 0;
    if (runId) {
      await closeSyncRun(sql, LOG, runId, {
        status: summary.failed > 0 && !houveSucesso ? "failed" : "completed",
        recordsRead: summary.queued,
        recordsWritten: summary.stored,
        recordsSkipped: summary.unchanged + summary.absent,
        error: summary.failed > 0
          ? `${summary.failed} funcionário(s) falharam nesta passada`
          : null,
      });
    }

    return new Response(JSON.stringify({ ok: true, summary }, null, 2), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Erro desconhecido.";
    console.error(`${LOG} Falha na sincronização de fotos:`, message);

    if (sql && runId) {
      try {
        await closeSyncRun(sql, LOG, runId, {
          status: "failed",
          recordsRead: 0,
          recordsWritten: 0,
          recordsSkipped: 0,
          error: message,
        });
      } catch (registro) {
        console.error(`${LOG} Falha também ao fechar a execução:`, registro);
      }
    }

    return new Response(JSON.stringify({ ok: false, error: message }, null, 2), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

Deno.serve((request) => handleRequest(request));
