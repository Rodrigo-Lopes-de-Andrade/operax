// Conexão direta ao Postgres para as Edge Functions — substitui supabase-js
// para qualquer acesso a `secullum` ou `app`, porque o PostgREST (usado por
// baixo do supabase-js) só alcança schemas na lista "Exposed schemas" do
// projeto (hoje: só `public`, `graphql_public` — e `secullum`/`app` NUNCA
// devem entrar nessa lista, ver CLAUDE.md). `service_role` ignora RLS, mas
// não ignora essa restrição do PostgREST — por isso a troca de schema via
// `supabase-js`'s `db: { schema }` não funciona aqui, mesmo com service_role.
//
// Usa o driver `postgres` (porsager) direto contra a connection string do
// Transaction Pooler (Supavisor/pgbouncer, porta 6543) — apropriado para
// Edge Functions serverless, que não devem manter conexões long-lived
// contra a porta direta (5432).
//
// Requer o secret `DATABASE_URL` (connection string do Transaction Pooler,
// com senha), configurado via `supabase secrets set DATABASE_URL=...` —
// NUNCA commitado, nunca passado em texto no chat.

import postgres from "postgres";

let sql: ReturnType<typeof postgres> | null = null;

export function getSql(): ReturnType<typeof postgres> {
  if (sql) return sql;
  const url = Deno.env.get("DATABASE_URL") ?? "";
  if (!url) {
    throw new Error(
      "DATABASE_URL ausente — configure via `supabase secrets set DATABASE_URL=<connection string do Transaction Pooler>`.",
    );
  }
  sql = postgres(url, {
    // Obrigatório com o Transaction Pooler: ele não sustenta prepared
    // statements entre requisições (conexões são reaproveitadas entre
    // clientes diferentes).
    prepare: false,
    // Uma invocação de Edge Function é uma unidade curta de trabalho — não
    // faz sentido manter um pool grande por instância.
    max: 1,
  });
  return sql;
}
