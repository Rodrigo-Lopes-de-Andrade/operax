import { TENANT_TIME_ZONE } from "@/lib/ponto/filters";

/**
 * Formatting of the numbers the screen shows. Two rules come from the design
 * and are not cosmetic:
 *
 *  - minutes are signed, and colour alone never carries the direction — the
 *    sign and the word travel with it;
 *  - the vocabulary is *desvio* and *indício*. Never "hora extra": the official
 *    record is the time-clock system, and a manager acting on a divergence
 *    between the two is the supplier's exposure.
 */

const MINUS = "−";

export type Direction = "surplus" | "shortfall" | "neutral" | (string & {});

export const DIRECTION_WORD: Record<string, string> = {
  surplus: "excedente",
  shortfall: "faltante",
  neutral: "sem par",
};

export function directionWord(direction: Direction): string {
  return DIRECTION_WORD[direction] ?? DIRECTION_WORD.neutral;
}

/** `+42`, `−15`, `0`. The typographic minus, not a hyphen — it aligns. */
export function formatSignedMinutes(minutes: number): string {
  if (minutes === 0) {
    return "0";
  }

  return minutes > 0 ? `+${minutes}` : `${MINUS}${Math.abs(minutes)}`;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}

/** `2h 15min` for a total, because 742 minutes says less than "12h 22min". */
export function formatDuration(minutes: number): string {
  const total = Math.abs(minutes);
  const hours = Math.floor(total / 60);
  const rest = total % 60;

  if (hours === 0) {
    return `${rest}min`;
  }

  return rest === 0 ? `${hours}h` : `${hours}h ${rest}min`;
}

/** `22/08` — the day as the table shows it. */
export function formatDayShort(isoDate: string): string {
  const [, month, day] = isoDate.split("-");

  return `${day}/${month}`;
}

export function formatDayLong(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);

  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function formatWeekday(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);

  return new Intl.DateTimeFormat("pt-BR", { weekday: "short", timeZone: "UTC" })
    .format(new Date(Date.UTC(year, month - 1, day)))
    .replace(".", "");
}

/** `08:12` from the `time` Postgres hands over as `08:12:00`. */
export function formatTime(value: string | null): string | null {
  return value ? value.slice(0, 5) : null;
}

/** `08:40` in the tenant's zone, from a timestamptz. */
export function formatClock(timestamp: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: TENANT_TIME_ZONE,
  }).format(new Date(timestamp));
}

/** `há 25 min`, `há 1h52`. The age of the data is never hidden in a tooltip. */
export function formatAge(minutes: number): string {
  if (minutes < 1) {
    return "agora";
  }
  if (minutes < 60) {
    return `há ${minutes} min`;
  }

  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;

  return `há ${hours}h${String(rest).padStart(2, "0")}`;
}

export function formatRange(de: string, ate: string): string {
  return de === ate
    ? formatDayLong(de)
    : `${formatDayShort(de)} a ${formatDayShort(ate)}`;
}
