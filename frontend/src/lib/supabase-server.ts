import { cookies } from "next/headers";
import { cache } from "react";
import type { SupabaseClient, User } from "@supabase/supabase-js";

import { createServerSupabaseClient } from "@/lib/supabase";

/** Supabase client bound to the cookies of the current request. */
export async function getServerSupabase(): Promise<SupabaseClient> {
  const cookieStore = await cookies();

  return createServerSupabaseClient({
    getAll: () => cookieStore.getAll(),
    setAll: (cookiesToSet) => {
      try {
        for (const { name, value, options } of cookiesToSet) {
          cookieStore.set(name, value, options);
        }
      } catch {
        // Server Components cannot write cookies. proxy.ts refreshes the
        // session on every request, so nothing is lost here.
      }
    },
  });
}

/**
 * The user of the current request, verified against the Supabase Auth server —
 * not merely decoded from the cookie. Returns null when there is no valid
 * session, which is what makes the protected layout fail closed.
 *
 * Authentication only. Role, organisational scope and sensitive-domain
 * permission are decided by RLS and by FastAPI; the UI just reflects them.
 */
export const getCurrentUser = cache(async (): Promise<User | null> => {
  const supabase = await getServerSupabase();
  const { data, error } = await supabase.auth.getUser();

  if (error) {
    return null;
  }

  return data.user;
});
