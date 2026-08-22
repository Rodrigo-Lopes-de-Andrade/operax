"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * A sidebar entry that knows whether it is the screen you are on.
 *
 * `usePathname` and not the query string on purpose: the cut of a screen is not
 * a different screen, so filtering the dashboard must not un-highlight it.
 */
export function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href;

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`rounded-[10px] px-3 py-2.5 text-sm font-bold transition-colors ${
        active
          ? "text-on-chrome bg-white/12"
          : "text-white/80 hover:bg-white/8 hover:text-white"
      }`}
    >
      {label}
    </Link>
  );
}
