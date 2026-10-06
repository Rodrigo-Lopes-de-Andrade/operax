import { NextResponse, type NextRequest } from "next/server";

import { LOGIN_PATH, PATHNAME_HEADER, safeNextPath } from "@/lib/navigation";
import { createServerSupabaseClient } from "@/lib/supabase-server";
import { CONVITE_PATH } from "@/lib/usuarios/url";

const PUBLIC_PATHS = new Set<string>([LOGIN_PATH]);

/**
 * Open to both sides, and bounced by neither. The invitation landing receives a
 * visitor with no session yet — the link in the e-mail is what opens one, in the
 * browser, from the URL fragment the server never sees — and it must not send a
 * signed-in visitor away either: the link may belong to another account than
 * the one already in this browser.
 */
const OPEN_PATHS = new Set<string>([CONVITE_PATH]);

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
  // Server Components cannot read the requested path. Carrying it forward is
  // what lets the protected layout redirect to the login without dropping the
  // deep link the alert message pointed at.
  const forward = () => {
    const headers = new Headers(request.headers);
    headers.set(
      PATHNAME_HEADER,
      `${request.nextUrl.pathname}${request.nextUrl.search}`,
    );
    return NextResponse.next({ request: { headers } });
  };

  let response = forward();

  const supabase = createServerSupabaseClient({
    getAll: () => request.cookies.getAll(),
    setAll: (cookiesToSet, headers) => {
      for (const { name, value } of cookiesToSet) {
        request.cookies.set(name, value);
      }

      // Rebuilt after the cookie jar changed, so the refreshed session travels
      // to the render as well.
      response = forward();

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

  if (OPEN_PATHS.has(pathname)) {
    return response;
  }

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
