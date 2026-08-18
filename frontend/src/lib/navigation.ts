export const LOGIN_PATH = "/login";
export const DEFAULT_AUTHENTICATED_PATH = "/dashboard";

/**
 * Normalises the `next` parameter used to send the user back to the screen the
 * link pointed at. Alert links travel through WhatsApp, so the value is
 * attacker-controlled: only a same-origin relative path survives, everything
 * else falls back to the default screen.
 */
export function safeNextPath(value: string | string[] | undefined | null) {
  const candidate = Array.isArray(value) ? value[0] : value;

  if (typeof candidate !== "string") {
    return DEFAULT_AUTHENTICATED_PATH;
  }

  // Rejects absolute URLs ("https://…"), protocol-relative ("//host") and the
  // backslash variant that some browsers still normalise to a host.
  if (!/^\/(?![/\\])/.test(candidate)) {
    return DEFAULT_AUTHENTICATED_PATH;
  }

  return candidate;
}
