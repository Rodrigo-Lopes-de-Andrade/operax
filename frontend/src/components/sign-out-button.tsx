"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { LOGIN_PATH } from "@/lib/navigation";
import { createBrowserSupabaseClient } from "@/lib/supabase";

/** Client Component: ends the session and sends the user back to the login. */
export function SignOutButton() {
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);

  async function signOut() {
    setLeaving(true);
    const supabase = createBrowserSupabaseClient();
    await supabase.auth.signOut();
    router.replace(LOGIN_PATH);
    router.refresh();
  }

  return (
    <Button variant="chrome" onClick={signOut} disabled={leaving}>
      {leaving ? <Spinner /> : null}
      {leaving ? "Saindo…" : "Sair"}
    </Button>
  );
}
