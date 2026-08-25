import Link from "next/link";

/**
 * The period picker. Rendered as links, not buttons: the cut lives in the URL,
 * so switching period is a navigation and the browser's back button walks the
 * manager's own filter history.
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  hrefFor,
  label,
}: {
  options: readonly { value: T; label: string }[];
  value: T;
  hrefFor: (value: T) => string;
  label: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="bg-muted border-line-subtle inline-flex gap-0.5 rounded-full border p-0.5"
    >
      {options.map((option) => (
        <Link
          key={option.value}
          href={hrefFor(option.value)}
          aria-current={option.value === value ? "true" : undefined}
          className={`rounded-full px-3.5 py-1.5 text-xs font-bold transition-colors ${
            option.value === value
              ? "bg-card text-ink shadow-[var(--shadow-xs)]"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          {option.label}
        </Link>
      ))}
    </div>
  );
}
