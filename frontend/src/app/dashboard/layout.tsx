import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { LOGIN_PATH } from "@/lib/navigation";
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
    redirect(LOGIN_PATH);
  }

  return (
    <SessionProvider user={{ id: user.id, email: user.email ?? "" }}>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
