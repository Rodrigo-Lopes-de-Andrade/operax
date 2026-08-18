import { headers } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { LOGIN_PATH, PATHNAME_HEADER, safeNextPath } from "@/lib/navigation";
import { getCurrentUser } from "@/lib/supabase-server";
import { SessionProvider } from "@/state/session";

/**
 * The authorisation decision for this whole area, taken on the server. proxy.ts
 * already redirects the anonymous visitor, but this check is what makes the
 * area fail closed if the proxy is ever bypassed or misconfigured.
 */
export default async function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  const user = await getCurrentUser();

  if (!user) {
    // A session that expires mid-navigation must not cost the deep link the
    // alert message pointed at. proxy.ts forwards the requested path.
    const requested = (await headers()).get(PATHNAME_HEADER);
    const query = new URLSearchParams({ next: safeNextPath(requested) });
    redirect(`${LOGIN_PATH}?${query}`);
  }

  return (
    <SessionProvider user={{ id: user.id, email: user.email ?? "" }}>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
