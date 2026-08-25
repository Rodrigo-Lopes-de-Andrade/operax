import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import type { Database } from "@/lib/database.types";
import { publicEnv } from "@/lib/env";

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
export function createBrowserSupabaseClient(): SupabaseClient<Database> {
  const env = publicEnv();

  return createBrowserClient<Database>(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  );
}
