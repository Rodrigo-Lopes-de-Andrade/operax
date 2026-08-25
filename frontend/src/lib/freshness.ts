import "server-only";

import { getServerSupabase } from "@/lib/supabase-server";

/**
 * How old the synced data is. Punches are read every 15 minutes and the rest of
 * the register every 30 (`docs/DECISAO-CADENCIA-SYNC.md`), so a manager looking
 * at the board at 09:05 must not read "nobody is late" out of a picture taken at
 * 08:50.
 *
 * `fn_data_freshness` answers per entity and derives the tenant from the
 * session — it takes no tenant parameter, so there is no way to probe another
 * one. The screen shows the *oldest* entity: the board is only as fresh as the
 * stalest thing on it.
 */
export type DataFreshness = {
  lastSyncAt: string;
  ageMinutes: number;
  isStale: boolean;
};

export async function loadFreshness(): Promise<DataFreshness | null> {
  const supabase = await getServerSupabase();
  const { data, error } = await supabase.rpc("fn_data_freshness", {});

  if (error || !data?.length) {
    return null;
  }

  return data
    .map((row) => ({
      lastSyncAt: row.last_sync_at,
      ageMinutes: row.age_minutes,
      isStale: row.is_stale,
    }))
    .reduce((oldest, row) =>
      row.ageMinutes > oldest.ageMinutes ? row : oldest,
    );
}
