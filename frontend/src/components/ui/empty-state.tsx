import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import type { Tone } from "@/components/ui/badge";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-muted text-ink-muted",
  brand: "bg-brand-soft/40 text-brand-strong",
  good: "bg-good-bg text-good",
  alert: "bg-alert-bg text-alert",
  bad: "bg-bad-bg text-bad",
};

/**
 * A day with no occurrence is a success, not an empty table — hence a tone.
 * Empty, stale and error are main-path states on this product, so they get a
 * real component instead of a dash.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  tone = "neutral",
  compact = false,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  tone?: Tone;
  compact?: boolean;
  children?: ReactNode;
}) {
  return (
    <div
      className={`flex flex-col items-center text-center ${compact ? "gap-2 py-6" : "gap-3 py-12"}`}
    >
      <span
        className={`flex items-center justify-center rounded-full ${TONE_CLASS[tone]} ${
          compact ? "size-11" : "size-16"
        }`}
      >
        <Icon size={compact ? 20 : 26} strokeWidth={2} aria-hidden />
      </span>
      <p className={`text-ink font-bold ${compact ? "text-md" : "text-lg"}`}>
        {title}
      </p>
      {description ? (
        <p className="text-ink-muted max-w-[520px] text-sm text-pretty">
          {description}
        </p>
      ) : null}
      {children ? (
        <div className="mt-1 flex items-center gap-2">{children}</div>
      ) : null}
    </div>
  );
}
