import type { ReactNode } from "react";

/**
 * Tones carry meaning, not decoration: `bad` is failure, never a deviation.
 * The direction of a deviation is violet/orange and lives in `SignedMinutes`.
 */
export type Tone = "neutral" | "brand" | "good" | "alert" | "bad";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-muted text-ink-muted",
  brand: "bg-brand-soft/40 text-brand-strong",
  good: "bg-good-bg text-good",
  alert: "bg-alert-bg text-alert",
  bad: "bg-bad-bg text-bad",
};

const DOT_CLASS: Record<Tone, string> = {
  neutral: "bg-ink-faint",
  brand: "bg-brand",
  good: "bg-good",
  alert: "bg-alert",
  bad: "bg-bad",
};

export function Badge({
  tone = "neutral",
  dot = false,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-2xs font-bold ${TONE_CLASS[tone]}`}
    >
      {dot ? (
        <span
          aria-hidden
          className={`size-1.5 rounded-full ${DOT_CLASS[tone]}`}
        />
      ) : null}
      {children}
    </span>
  );
}

/** Dashed chip. Reserved for a state that is not a fact yet — an unconfirmed roster. */
export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="border-line-strong text-ink-faint text-2xs inline-flex items-center gap-1.5 rounded-full border border-dashed px-2.5 py-1 font-semibold">
      {children}
    </span>
  );
}
