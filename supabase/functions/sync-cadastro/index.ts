// Edge Function da sincronização cadastral (Sprint 1 — docs/03, docs/04,
// sprints/sprint-01-integracao-secullum.md). Agendada via Cron Trigger
// (pg_cron, ver supabase/migrations/20260812131000_sync_cadastro_cron.sql —
// ADR-003), mas também pode ser invocada manualmente para o entregável
// demonstrável da sprint:
//
//   supabase functions invoke sync-cadastro
//
// ou, servindo localmente (exige Docker Desktop):
//   supabase functions serve sync-cadastro --env-file .env --no-verify-jwt
//   curl -s -X POST http://127.0.0.1:54321/functions/v1/sync-cadastro
//
// Faz três chamadas de leitura ao Secullum: GET /Funcionarios, GET
// /Horarios e GET /FuncionariosAfastamentos (5º e último endpoint do escopo,
// ADR-010 — adicionado em 2026-08-13; eram duas até então). GET /Estruturas
// e GET /Empresas NUNCA são chamadas — Estrutura e Empresa já vêm aninhadas
// em cada Funcionario (ver docs/03-integracao-secullum.md — "Resolução do
// gestor").
//
// Resposta: apenas contadores e avisos SEM PII (nomes/e-mails nunca aparecem
// — avisos referenciam sempre por Id, nunca por Descricao/Nome, ver
// docs/06-seguranca-lgpd.md).
//
// Toda execução deixa uma linha em `app.sync_run`, do mesmo jeito que a
// `sync-batidas`. Enquanto quem sincronizava produção era o runner da Vercel,
// esse rastro existia em `app.job_execucao` — foi por ele que a falha de
// autenticação de 01/09 03:30 ficou visível. Depois da troca de runner esse
// diário some, e sem esta gravação uma falha de cadastro não apareceria em
// tabela nenhuma: `fn_data_freshness` agrupa pelo que existe em `app.sync_run`,
// então entidade que nunca escreve não vira linha velha — vira ausência, que
// nenhum painel lê como problema. Ver docs/RUNBOOK-JANELA-CONVERGENCIA.md,
// passo 7, item 6.
//
// A linha é reivindicada ANTES de a origem ser lida, e é ela o lock de
// sobreposição (migration 34): uma segunda invocação simultânea recebe 409 e
// não chama o Secullum. Depois da troca de runner isso deixa de ser hipótese —
// quem barra a função é o `verify_jwt` do gateway, que aceita a anon key, que é
// pública.

import { createSecullumClientFromEnv } from "../_shared/secullum-client.ts";
import { runCadastroSync } from "../_shared/cadastro-sync.ts";
import { createSupabaseSyncRepositoryFromEnv } from "../_shared/supabase-cadastro-repository.ts";
import { getSql, type Sql } from "../_shared/postgres-client.ts";
import { claimSyncRun, closeSyncRun } from "../_shared/sync-run.ts";
import { requireSyncSecret } from "../_shared/require-secret.ts";

/** Prefixo de log — o mesmo que o resto da função usa. */
const LOG = "[sync-cadastro]";

/**
 * Nome da entidade em `app.sync_run.entity` — o exemplo que a própria migration
 * 09 dá para a coluna (`'Funcionario', 'Batida', 'payroll_entry'...`).
 *
 * Uma linha por passada, e não uma por entidade sincronizada: `runCadastroSync`
 * não tem `try/catch` em fase nenhuma, então as 17 entidades do resumo
 * terminam sempre com o MESMO `started_at`, o MESMO `finished_at` e o MESMO
 * status. Dezessete linhas idênticas em três colunas não acrescentam sinal a
 * quem lê — `fn_data_freshness` reduz tudo à entidade mais velha — e
 * multiplicariam o diário por 17 a cada meia hora.
 */
const ENTITY = "Funcionario";

async function handleRequest(request: Request): Promise<Response> {
  // Antes de tudo: antes de abrir conexão e antes de falar com a origem. Metade
  // do que o segredo protege é a carga que uma invocação não autorizada geraria.
  const recusa = await requireSyncSecret(request, LOG);
  if (recusa) return recusa;

  let sql: Sql | null = null;
  let runId: string | null = null;

  try {
    // A reivindicação vem ANTES do login, e a ordem é o ponto duas vezes: a
    // falha que mais precisa de rastro é a de autenticação, e o lock só protege
    // a origem se for tomado antes de alguém falar com ela.
    sql = getSql();
    const claim = await claimSyncRun(sql, LOG, ENTITY, "incremental");
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

    const repo = createSupabaseSyncRepositoryFromEnv();
    const summary = await runCadastroSync(secullum, repo);

    if (runId) {
      await closeSyncRun(sql, LOG, runId, {
        status: "completed",
        recordsRead: summary.employeesFetched,
        recordsWritten: summary.employeesUpserted,
        recordsSkipped: summary.employeesSkipped,
        error: null,
      });
    }

    return new Response(JSON.stringify({ ok: true, summary }, null, 2), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Erro desconhecido.";
    console.error(`${LOG} Falha na sincronização cadastral:`, message);

    // O fechamento falha aberto: um erro ao registrar não pode esconder o erro
    // que estamos reportando. Os contadores vão zerados porque `runCadastroSync`
    // lançou — o resumo dele morreu junto —, e é o `error` que carrega o motivo.
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
