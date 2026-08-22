"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Re-renders the server components of the current route on a timer.
 *
 * `router.refresh()` and not `location.reload()`: a full reload on a screen
 * that runs for weeks re-downloads the bundle, loses the scroll and flashes
 * white in a dark corridor every few minutes. This asks the server for the same
 * route again and swaps the tree.
 *
 * The interval is not the data's cadence and should not try to be. The sync
 * runs every 30 minutes; this runs often enough that the age on screen never
 * lies by much, and no more often than that — the board reads a handful of
 * aggregates, but it reads them forever.
 */
export function AutoRefresh({ seconds }: { seconds: number }) {
  const router = useRouter();

  useEffect(() => {
    const timer = setInterval(() => router.refresh(), seconds * 1000);

    return () => clearInterval(timer);
  }, [router, seconds]);

  return null;
}
