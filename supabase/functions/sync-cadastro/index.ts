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

import { createSecullumClientFromEnv } from "../_shared/secullum-client.ts";
import { runCadastroSync } from "../_shared/cadastro-sync.ts";
import { createSupabaseSyncRepositoryFromEnv } from "../_shared/supabase-cadastro-repository.ts";

async function handleRequest(): Promise<Response> {
  try {
    const secullum = createSecullumClientFromEnv();
    await secullum.login();

    const repo = createSupabaseSyncRepositoryFromEnv();
    const summary = await runCadastroSync(secullum, repo);

    return new Response(JSON.stringify({ ok: true, summary }, null, 2), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Erro desconhecido.";
    console.error("[sync-cadastro] Falha na sincronização cadastral:", message);
    return new Response(JSON.stringify({ ok: false, error: message }, null, 2), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

Deno.serve(() => handleRequest());
