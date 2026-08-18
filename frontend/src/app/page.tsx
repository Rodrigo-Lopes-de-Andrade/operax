import { redirect } from "next/navigation";

import { DEFAULT_AUTHENTICATED_PATH } from "@/lib/navigation";

export default function HomePage() {
  // proxy.ts decides whether this ends at the dashboard or at the login.
  redirect(DEFAULT_AUTHENTICATED_PATH);
}
