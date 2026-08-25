import Link from "next/link";

export type TabItem = {
  value: string;
  label: string;
  href: string;
  count?: number;
};

/**
 * Abas de detalhe, renderizadas como links.
 *
 * Links e não botões pelo mesmo motivo do seletor de período: a aba aberta é
 * parte do recorte, mora na query string, e o botão "voltar" do navegador tem de
 * andar por ela.
 *
 * A lista que chega aqui já é a lista de abas que **existem** para quem está
 * olhando. Uma aba que o papel não alcança não chega desabilitada: ela não chega.
 * Cadeado é informação — quem não pode ver remuneração não deveria descobrir na
 * interface que existe uma aba de remuneração.
 */
export function Tabs({
  items,
  value,
  label,
}: {
  items: TabItem[];
  value: string;
  label: string;
}) {
  return (
    <nav
      aria-label={label}
      className="border-line-subtle flex gap-1 overflow-x-auto border-b"
    >
      {items.map((item) => {
        const active = item.value === value;

        return (
          <Link
            key={item.value}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`flex shrink-0 items-center gap-2 px-3.5 py-2.5 text-sm transition-colors ${
              active
                ? "text-ink border-brand border-b-2 font-bold"
                : "text-ink-muted hover:text-ink border-b-2 border-transparent font-semibold"
            }`}
          >
            {item.label}
            {item.count === undefined ? null : (
              <span
                className={`text-2xs rounded-full px-1.5 py-0.5 font-bold ${
                  active
                    ? "bg-brand-soft/40 text-brand-strong"
                    : "bg-muted text-ink-faint"
                }`}
              >
                {item.count}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
