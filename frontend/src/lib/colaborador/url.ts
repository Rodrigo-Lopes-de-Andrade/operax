import { DEFAULT_PERIOD, type Period } from "@/lib/ponto/filters";

/** Individual consultation. One person, one period, both in the URL. */
export function colaboradorHref(
  employeeId: string,
  period: Period = DEFAULT_PERIOD,
): string {
  const path = `/dashboard/colaborador/${employeeId}`;

  return period === DEFAULT_PERIOD ? path : `${path}?per=${period}`;
}
