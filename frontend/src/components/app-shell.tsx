import type { ReactNode } from "react";

import { Brand } from "@/components/brand";
import { SignOutButton } from "@/components/sign-out-button";
import { UserBadge } from "@/components/user-badge";

/**
 * Authenticated chrome. Navigation, the data-freshness indicator and the
 * screens themselves arrive with the dashboard sprint; what exists here is the
 * frame and the identity of whoever is signed in.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="bg-chrome flex items-center justify-between gap-4 px-7 py-4">
        <Brand />
        <div className="flex items-center gap-4">
          <UserBadge />
          <SignOutButton />
        </div>
      </header>
      <main className="mx-auto w-full max-w-[var(--content-max)] flex-1 px-7 py-6">
        {children}
      </main>
    </div>
  );
}
