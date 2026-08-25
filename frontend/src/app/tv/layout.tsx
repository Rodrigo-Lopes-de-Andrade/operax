import { headers } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { LOGIN_PATH, PATHNAME_HEADER, safeNextPath } from "@/lib/navigation";
import { getCurrentUser } from "@/lib/supabase-server";

/**
 * The wall board is authenticated like everything else — a browser signed in
 * once on the TV, and the SDK refreshing the session from then on. It is a
 * screen with no operator, not a screen with no session: RLS still decides what
 * the numbers cover, so an unauthenticated board would simply be an empty one.
 *
 * What it does not get is the app chrome. No sidebar, no user badge and no
 * sign-out button: nobody is sitting here, and the only person who ever touches
 * this screen is whoever bumps into it.
 *
 * `data-theme="dark"` is scoped to this subtree. The board is dark because a
 * lit rectangle at three metres in a corridor is unreadable, which has nothing
 * to do with the manager's OS preference — so this is an attribute, not a media
 * query.
 */
export default async function TvLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();

  if (!user) {
    const requested = (await headers()).get(PATHNAME_HEADER);
    const query = new URLSearchParams({ next: safeNextPath(requested) });
    redirect(`${LOGIN_PATH}?${query}`);
  }

  return (
    <div data-theme="dark" className="bg-canvas text-ink min-h-dvh">
      {children}
    </div>
  );
}
