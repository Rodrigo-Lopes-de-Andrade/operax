import Link from "next/link";
import type { ReactNode } from "react";

import { Brand } from "@/components/brand";
import { DataFreshness } from "@/components/data-freshness";
import { NavLink } from "@/components/nav-link";
import { SignOutButton } from "@/components/sign-out-button";
import { UserBadge } from "@/components/user-badge";
import { MONITOR_PATH } from "@/lib/monitor/url";
import { PONTO_PATH } from "@/lib/ponto/url";
import { TV_PATH } from "@/lib/tv/url";

/**
 * Authenticated chrome: a 264px navy sidebar and an 84px header carrying the
 * permanent data-age pill.
 *
 * The navigation lists only what exists. The individual consultation is reached
 * from a row, not from here, because it is always about somebody you were
 * already looking at. Payroll, alert rules, the assistant and administration
 * arrive with their own screens — a nav item that leads nowhere reads as a
 * defect, and a disabled one without a reason reads worse.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="bg-canvas flex min-h-dvh">
      <aside className="bg-chrome hidden w-[var(--sidebar-width)] shrink-0 flex-col lg:flex">
        <div className="flex h-[var(--header-height)] items-center px-6">
          <Link href={PONTO_PATH}>
            <Brand />
          </Link>
        </div>

        <nav aria-label="Seções" className="flex flex-col gap-1 px-4 py-2">
          <p className="text-2xs px-3 py-2 font-bold tracking-[0.08em] text-white/80 uppercase">
            Operação
          </p>
          <NavLink href={PONTO_PATH} label="Gestão de ponto" />
          <NavLink href={MONITOR_PATH} label="Monitor diário" />
          <NavLink href={TV_PATH} label="Painel de TV" />
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="bg-chrome flex h-[var(--header-height)] items-center justify-between gap-4 px-6">
          <Link href={PONTO_PATH} className="lg:hidden">
            <Brand />
          </Link>
          <DataFreshness />
          <div className="flex items-center gap-4">
            <UserBadge />
            <SignOutButton />
          </div>
        </header>

        <main className="mx-auto w-full max-w-[var(--content-max)] flex-1 px-6 py-6">
          {children}
        </main>
      </div>
    </div>
  );
}
