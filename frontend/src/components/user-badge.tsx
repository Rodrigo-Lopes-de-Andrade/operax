"use client";

import { useSession } from "@/state/session";

/** Client Component: reads the session context the shell provides. */
export function UserBadge() {
  const { email } = useSession();
  const initials = email.slice(0, 2).toUpperCase();

  return (
    <span className="flex items-center gap-2.5">
      {/* Avatars are initials — the product never renders a photo. */}
      <span className="text-on-chrome flex size-8 items-center justify-center rounded-full bg-white/12 text-xs font-bold">
        {initials}
      </span>
      <span className="text-on-chrome max-w-56 truncate text-sm font-medium">
        {email}
      </span>
    </span>
  );
}
