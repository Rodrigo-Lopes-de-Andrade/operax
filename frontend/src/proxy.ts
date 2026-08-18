import { NextResponse, type NextRequest } from "next/server";

import { LOGIN_PATH, safeNextPath } from "@/lib/navigation";
import { createServerSupabaseClient } from "@/lib/supabase";

const PUBLIC_PATHS = new Set<string>([LOGIN_PATH]);

/**
 * Runs before every rendered route. Two jobs:
 *
 * 1. refresh the Supabase session cookie, which only a place that owns the
 *    response can do;
 * 2. redirect the anonymous visitor to the login, keeping where they were
 *    going so the alert link survives the detour.
 *
 * This is the optimistic check. The real decision is taken again by the
 * protected layout, by RLS on every Supabase read and by FastAPI on every
 * sensitive one.
 */
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerSupabaseClient({
    getAll: () => request.cookies.getAll(),
    setAll: (cookiesToSet, headers) => {
      for (const { name, value } of cookiesToSet) {
        request.cookies.set(name, value);
      }

      response = NextResponse.next({ request });

      for (const { name, value, options } of cookiesToSet) {
        response.cookies.set(name, value, options);
      }

      // Answers that set auth cookies must not be cached by a CDN.
      for (const [header, value] of Object.entries(headers)) {
        response.headers.set(header, value);
      }
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname, search } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.has(pathname);

  if (!user && !isPublic) {
    const login = new URL(LOGIN_PATH, request.url);
    login.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }

  if (user && isPublic) {
    const target = safeNextPath(request.nextUrl.searchParams.get("next"));
    return NextResponse.redirect(new URL(target, request.url));
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
