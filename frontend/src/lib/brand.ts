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
};

const FASTPARK: Brand = {
  name: "FastPark",
  glyph: "square-parking",
};

/** The brand of the current tenant. One tenant today, resolved here tomorrow. */
export function currentBrand(): Brand {
  return FASTPARK;
}

/** `Gestão de ponto · FastPark` — the title bar carries the client, not us. */
export function pageTitle(screen: string): string {
  return `${screen} · ${currentBrand().name}`;
}
