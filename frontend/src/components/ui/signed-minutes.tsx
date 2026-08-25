import {
  directionWord,
  formatSignedMinutes,
  type Direction,
} from "@/lib/ponto/format";

const COLOR: Record<string, string> = {
  surplus: "text-surplus",
  shortfall: "text-shortfall",
  neutral: "text-ink-muted",
};

/**
 * The minutes of a deviation, signed and coloured — and never colour alone.
 * On a phone in the sun, hue is a suggestion, so the sign and the word are part
 * of the value, not an annotation next to it.
 */
export function SignedMinutes({
  minutes,
  direction,
  size = "md",
  word = true,
}: {
  minutes: number;
  direction: Direction;
  size?: "sm" | "md" | "lg";
  word?: boolean;
}) {
  const sizeClass = { sm: "text-sm", md: "text-md", lg: "text-2xl" }[size];

  return (
    <span className="inline-flex items-baseline gap-1.5 tabular-nums">
      <span
        className={`font-extrabold ${sizeClass} ${COLOR[direction] ?? COLOR.neutral}`}
      >
        {formatSignedMinutes(minutes)}
      </span>
      {word ? (
        <span className="text-ink-muted text-2xs font-semibold">
          {directionWord(direction)}
        </span>
      ) : null}
    </span>
  );
}
