export const LOGIN_PATH = "/login";
export const DEFAULT_AUTHENTICATED_PATH = "/dashboard";

/**
 * Header proxy.ts uses to tell the server components which path the browser
 * actually asked for, so a redirect from a layout can keep the deep link.
 */
export const PATHNAME_HEADER = "x-operax-pathname";

/**
 * Unreachable by construction (RFC 6761 reserves `.invalid`). It exists only
 * so a candidate can be parsed the same way the sinks parse it.
 */
const SENTINEL_ORIGIN = "https://operax.invalid";

/**
 * Normalises the `next` parameter used to send the user back to the screen the
 * link pointed at. Alert links travel through WhatsApp, so the value is
 * attacker-controlled.
 *
 * The check is made on the parse, not on the string: the URL parser strips
 * TAB, LF and CR before parsing, so `/<TAB>/evil.test` looks relative to a
 * regex and resolves to `//evil.test` to everyone downstream. Whatever the
 * parser understands is what `new URL()` in proxy.ts and `router.replace()` in
 * the sign-in form will act on, so that is what has to be judged — and what is
 * returned, already normalised, instead of the raw input.
 *
 * A leading `/` is still required before parsing: the parser also trims
 * leading whitespace, and " //evil.test" must not become an authority.
 *
 * What comes out is then judged by its **form**, not by resolving it again:
 * the path normaliser eats dot segments (`.`, `..`, `%2e`) and can promote the
 * slash behind them to the first character of the path, turning
 * `/.//evil.test` into the authority `//evil.test`. Re-resolving against the
 * sentinel cannot decide that, because the sentinel is not where the sinks
 * resolve — `//operax.invalid` is same-origin to that base and another host to
 * `new URL(target, request.url)`. A value that starts with `//` or `/\\` is an
 * authority to every parser, whatever base it is given, and that is a property
 * of the string alone.
 *
 * The login is refused as a destination: every hop of
 * `/login?next=/login?next=…` is same-origin, so the chain would be accepted
 * one link at a time until the browser gives up with ERR_TOO_MANY_REDIRECTS —
 * on the manager who is already signed in and just tapped the alert.
 *
 * The fragment does not survive: `/dashboard#drawer` comes back as
 * `/dashboard`. Filter state lives in the query string (CLAUDE.md), so
 * nothing is lost today — but a drawer moved to the hash would be.
 */
export function safeNextPath(value: string | string[] | undefined | null) {
  const candidate = Array.isArray(value) ? value[0] : value;

  if (typeof candidate !== "string" || !candidate.startsWith("/")) {
    return DEFAULT_AUTHENTICATED_PATH;
  }

  let resolved: URL;

  try {
    resolved = new URL(candidate, SENTINEL_ORIGIN);
  } catch {
    return DEFAULT_AUTHENTICATED_PATH;
  }

  if (resolved.origin !== SENTINEL_ORIGIN) {
    return DEFAULT_AUTHENTICATED_PATH;
  }

  if (resolved.pathname === LOGIN_PATH) {
    return DEFAULT_AUTHENTICATED_PATH;
  }

  const normalised = `${resolved.pathname}${resolved.search}`;

  // An authority is what starts with "//" or "/\\", to any parser and against
  // any base. The parser normalises the backslash spelling away before it can
  // reach here, but the check states the invariant instead of depending on
  // that.
  if (
    normalised[0] !== "/" ||
    normalised[1] === "/" ||
    normalised[1] === "\\"
  ) {
    return DEFAULT_AUTHENTICATED_PATH;
  }

  return normalised;
}
