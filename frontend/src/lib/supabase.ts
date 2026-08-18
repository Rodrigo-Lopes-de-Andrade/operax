import {
  createBrowserClient,
  createServerClient,
  type CookieMethodsServer,
} from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { publicEnv } from "@/lib/env";

// TODO (pendencia) Type both clients with the output of
// `supabase gen types typescript` (as src/lib/database.types.ts) once a
// Supabase project exists. Table types are never hand-written (CLAUDE.md).

/**
 * Caminho 1 do contrato — the browser talks to Supabase directly with the anon
 * key, and only for non-sensitive aggregates: vw_deviation_summary_by_unit,
 * vw_deviation_daily_trend, vw_deviation_by_employee_day, vw_unit, vw_employee
 * and the fn_* RPCs. RLS filters tenant and scope on its own: the client never
 * sends tenant_id, and anon by itself reads nothing — the session has to be
 * authenticated.
 *
 * Individual, sensitive or write access is Caminho 2 and goes through
 * src/lib/api.ts.
 */
export function createBrowserSupabaseClient(): SupabaseClient {
  const env = publicEnv();

  return createBrowserClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  );
}

/**
 * Same anon key, server side — never the service_role key, which lives in the
 * FastAPI backend alone.
 *
 * The cookie adapter is injected so this module stays free of `next/headers`
 * and can be shared by proxy.ts (which owns the response) and by Server
 * Components (see src/lib/supabase-server.ts).
 */
export function createServerSupabaseClient(
  cookies: CookieMethodsServer,
): SupabaseClient {
  const env = publicEnv();

  return createServerClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    { cookies },
  );
}
