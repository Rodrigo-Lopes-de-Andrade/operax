/**
 * Horizontal ranking: label on the left, tabular value on the right, bar
 * underneath. `display` exists so a row can read "4 · 326 min" instead of a
 * bare count.
 */
export type RankbarItem = {
  key: string;
  label: string;
  value: number;
  display?: string;
  href?: string;
};

export function Rankbar({
  items,
  color = "var(--brand)",
}: {
  items: RankbarItem[];
  color?: string;
}) {
  const top = Math.max(...items.map((item) => item.value), 1);

  return (
    <ul className="flex flex-col gap-3">
      {items.map((item) => (
        <li key={item.key} className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-ink-body truncate text-sm font-semibold">
              {item.label}
            </span>
            <span className="text-ink text-sm font-bold tabular-nums">
              {item.display ?? item.value}
            </span>
          </div>
          <div className="bg-muted h-1.5 overflow-hidden rounded-full">
            <div
              className="h-full rounded-full"
              style={{
                width: `${(item.value / top) * 100}%`,
                background: color,
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
