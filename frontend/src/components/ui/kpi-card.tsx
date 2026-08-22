import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`bg-card border-line-subtle rounded-[18px] border shadow-[var(--shadow-sm)] ${className}`}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  eyebrow,
  title,
  note,
  action,
}: {
  eyebrow?: string;
  title: string;
  note?: string;
  action?: ReactNode;
}) {
  return (
    <header className="border-line-subtle flex items-start justify-between gap-4 border-b px-5 py-4">
      <div>
        {eyebrow ? (
          <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="text-ink text-md font-extrabold">{title}</h2>
        {note ? <p className="text-ink-muted mt-0.5 text-xs">{note}</p> : null}
      </div>
      {action}
    </header>
  );
}

/** The headline figure of a cut. `note` is where the caveat goes — never a tooltip. */
export function KpiCard({
  eyebrow,
  value,
  note,
  children,
}: {
  eyebrow: string;
  value: ReactNode;
  note?: string;
  children?: ReactNode;
}) {
  return (
    <Card className="flex flex-col gap-3 p-5">
      <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
        {eyebrow}
      </p>
      <p className="text-ink text-3xl leading-none font-extrabold tabular-nums">
        {value}
      </p>
      {children}
      {note ? (
        <p className="text-ink-muted text-xs text-pretty">{note}</p>
      ) : null}
    </Card>
  );
}
