"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, type ReactNode } from "react";

import { createBrowserSupabaseClient } from "@/lib/supabase";

/**
 * What the interface is allowed to know about the signed-in user: identity
 * only. Role, scope and sensitive-domain permission are not kept here on
 * purpose — they are decided by RLS and by FastAPI on every read.
 */
export type SessionUser = {
  id: string;
  email: string;
};

const SessionContext = createContext<SessionUser | null>(null);

type SessionProviderProps = {
  user: SessionUser;
  children: ReactNode;
};

export function SessionProvider({ user, children }: SessionProviderProps) {
  const router = useRouter();

  // Client Component: it subscribes to the Supabase SDK. Signing out in
  // another tab, or a revoked refresh token, has to reach this tab too — and
  // the server re-decides on refresh, this only asks it to.
  useEffect(() => {
    const supabase = createBrowserSupabaseClient();
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN" || event === "SIGNED_OUT") {
        router.refresh();
      }
    });

    return () => data.subscription.unsubscribe();
  }, [router]);

  return (
    <SessionContext.Provider value={user}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionUser {
  const user = useContext(SessionContext);

  if (!user) {
    throw new Error("useSession requires a <SessionProvider> above it");
  }

  return user;
}
