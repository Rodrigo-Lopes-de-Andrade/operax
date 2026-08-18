import type { ReactNode } from "react";

/** Failure banner. Red is for failure only — never for a deviation. */
export function Alert({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="bg-bad-bg text-bad rounded-[10px] px-3 py-2 text-sm font-medium"
    >
      {children}
    </p>
  );
}
