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
 * The same judgement is then applied to what comes out, because the path
 * normaliser eats dot segments (`.`, `..`, `%2e`) and can promote the slash
 * behind them to the first character of the path — turning `/.//evil.test`
 * into the authority `//evil.test` that the input never spelled. Judging the
 * result instead of listing its spellings is what keeps the next exotic form
 * from reopening this.
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

  const normalised = `${resolved.pathname}${resolved.search}`;

  try {
    if (new URL(normalised, SENTINEL_ORIGIN).origin !== SENTINEL_ORIGIN) {
      return DEFAULT_AUTHENTICATED_PATH;
    }
  } catch {
    // "//" on its own parses as an empty authority and throws in the sink,
    // which in the proxy is a 500 on the login of everyone already signed in.
    return DEFAULT_AUTHENTICATED_PATH;
  }

  return normalised;
}
