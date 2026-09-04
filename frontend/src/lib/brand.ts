/**
 * The product is white-label: what the user sees is the tenant's brand, never
 * the vendor's. "OperaX" is the product's name in this repository, in
 * identifiers and in the documents — it does not appear on any surface.
 *
 * A brand is therefore configuration, not a constant: a name, a wordmark, and a
 * set of token values. Components never read a brand colour, only a semantic
 * alias, so a second tenant is a second entry here and nothing else.
 *
 * Where the brand is stored per tenant is still open — a column on `app.tenant`
 * is the obvious home, and that is a schema decision. Until it is taken, the
 * registry is here and FastPark is the only entry, which is also the truth: it
 * is the anchor client and the first theme.
 */

export type Brand = {
  /** What the user reads. Also the suffix of every page title. */
  name: string;
  /** Lucide glyph standing in for the mark until the client ships an asset. */
  glyph: "square-parking";
  /**
   * The `data-brand` value the CSS keys on. Every token of this brand lives
   * under `[data-brand="<slug>"]` in `globals.css`, and components read only the
   * semantic aliases — never a Pantone. If a second tenant breaks a screen, the
   * theme went to the wrong place, and that is the test.
   */
  slug: string;
  /** Where the login lives, in lower case and without protocol. */
  hosts: readonly string[];
};

const FASTPARK: Brand = {
  name: "FastPark",
  glyph: "square-parking",
  slug: "fastpark",
  hosts: ["app.fastparks.com.br", "operaxfonted.vercel.app", "localhost"],
};

const BRANDS: readonly Brand[] = [FASTPARK];

/** The brand of the current tenant. One tenant today, resolved here tomorrow. */
export function currentBrand(): Brand {
  return FASTPARK;
}

/**
 * The brand for a host name — the only resolution that works BEFORE a session.
 *
 * The login is the one screen with no tenant yet: there is no token to read a
 * `tenant_id` from, so the brand cannot come from the session. The host can,
 * because it is already per client — `app.fastparks.com.br` is the FastPark
 * address and nobody else's.
 *
 * ⚠️ Falls back to the first brand rather than to an unbranded screen. An
 * unknown host today means a preview URL or a new alias, and showing a blank
 * login for it would be a worse failure than showing the anchor client's. The
 * day a second tenant exists, an unknown host stops being harmless and this
 * fallback becomes the thing to revisit — which is why it is written down.
 */
export function brandForHost(host: string | null | undefined): Brand {
  const clean = (host ?? "").toLowerCase().split(":")[0]?.trim() ?? "";
  return (
    BRANDS.find((brand) =>
      brand.hosts.some(
        (known) => clean === known || clean.endsWith(`.${known}`),
      ),
    ) ?? FASTPARK
  );
}

/** `Gestão de ponto · FastPark` — the title bar carries the client, not us. */
export function pageTitle(screen: string): string {
  return `${screen} · ${currentBrand().name}`;
}
