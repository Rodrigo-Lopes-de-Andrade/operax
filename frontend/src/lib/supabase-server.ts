import { createServerClient, type CookieMethodsServer } from "@supabase/ssr";
import type { SupabaseClient, User } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import { cache } from "react";

import { publicEnv } from "@/lib/env";

/**
 * Same anon key as the browser — never the service_role key, which lives in
 * the FastAPI backend alone.
 *
 * The cookie adapter is a parameter because the two server-side callers own
 * different things: proxy.ts owns the response and can write refreshed
 * cookies, a Server Component cannot. Keeping every server client in this
 * module is also what keeps `createServerClient` out of the browser bundle.
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
