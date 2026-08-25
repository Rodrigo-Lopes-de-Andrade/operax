import "server-only";

import { cache } from "react";

import { ApiError, requestApi } from "@/lib/api";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Who the backend says the caller is. `/me` is the only place the panel learns
 * a role, and it learns it from the backend, never from a claim it could read
 * itself: the role lives in `app.tenant_member` and FastAPI resolves it from the
 * validated token.
 *
 * The role decides **navigation** and nothing else. What a screen may show is
 * decided by RLS and by the backend on every read — a role that reaches the
 * Colaboradores tab still sees only the domains and the units its permissions
 * allow, and a role that does not reach the tab is refused by the API even if it
 * types the URL.
 */
export type Identity = {
  user_id: string;
  email: string | null;
  tenant_id: string;
  role: string;
};

/**
 * The roles the HR area is offered to. `owner`, `hr` and `personnel` are the
 * three `util.is_admin` accepts — they read and write. `executive` reads and
 * does not write, which is why the edit button is decided by `can_write` from
 * the API and not by this list.
 */
export const HR_ROLES = ["owner", "hr", "personnel", "executive"] as const;

export function reachesHr(role: string | undefined): boolean {
  return (HR_ROLES as readonly string[]).includes(role ?? "");
}

/**
 * Os três papéis que `util.is_admin` aceita — os que escrevem. `executive` está
 * fora, e essa é a diferença entre esta lista e `HR_ROLES`: ele lê a área de RH
 * e não cura nada. Curadoria é escrita, e escrita é `is_admin`.
 */
export const ADMIN_ROLES = ["owner", "hr", "personnel"] as const;

export function isAdmin(role: string | undefined): boolean {
  return (ADMIN_ROLES as readonly string[]).includes(role ?? "");
}

/**
 * Cached per request: the shell asks for it, and so does any page that needs to
 * fail closed on a deep link. `cache` makes that one call, not three.
 */
export const loadIdentity = cache(async (): Promise<Identity | null> => {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;

  if (!accessToken) {
    return null;
  }

  try {
    return await requestApi<Identity>("/me", { accessToken });
  } catch (error) {
    // A user with no active membership gets 403 here. That is not an outage —
    // it is somebody who has signed in and belongs to no tenant yet, and the
    // shell has to render without an HR section rather than crash.
    if (
      error instanceof ApiError &&
      (error.status === 403 || error.status === 401)
    ) {
      return null;
    }

    throw error;
  }
});
